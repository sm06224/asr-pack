"""ONNX の `MatMul(x, Transpose(<initializer>))` を `MatMul(x, <転置済みの initializer>)` に畳む。

なぜ要るか(2026-10-03 実測、PKC3 #772):
  whisper の decoder は出力の射影(proj_out)が埋め込み(embed_tokens)と**重みを共有**しており、
  optimum の export は `MatMul(hidden, Transpose(embed_tokens.weight))` の形で出す。
  transformers.js の q8 量子化は `MatMulConstBOnly=True` ── B が initializer でないと**量子化しない**
  (log: `Ignore MatMul due to non constant B: /optimum::if:else_branch/[/proj_out/MatMul]`)。
  その結果 base の decoder(q8)が 158MB(うち 106MB = 51865×512 の fp32 がそのまま)になった。
  Transpose を定数へ畳めば B が initializer になり、量子化が当たる(fp32 106MB → q8 約 27MB)。

⚠ merged decoder は `If` の then / else の 2 つの subgraph に decoder を持つ。Transpose は subgraph の中、
  initializer は外の graph に在るので、**subgraph を再帰で辿り、新しい initializer は外の graph へ足す**。
⚠ 元の initializer は消さない(Gather = 埋め込みの側がまだ読む)。fp32 の model は一時的に大きくなるが、
  量子化の後は小さくなる(配るのは量子化した物だけ)。

使い方: python tools/fold_tied_transpose.py <in.onnx> <out.onnx>
終了コード: 0 = 畳んだ(件数を出す) / 2 = 1 件も畳めなかった(前提が崩れている ── 止まる側)
"""
import sys
import numpy as np
import onnx
from onnx import numpy_helper


def main(src: str, dst: str) -> int:
    model = onnx.load(src, load_external_data=True)
    top = model.graph
    inits = {i.name: i for i in top.initializer}
    folded = 0
    added = {}

    def walk(graph, scope_inits):
        nonlocal folded
        local = dict(scope_inits)
        for i in graph.initializer:
            local[i.name] = i
        # Transpose(initializer) の出力名 → (元の initializer 名, perm)
        transposes = {}
        for n in graph.node:
            if n.op_type == 'Transpose' and len(n.input) == 1 and n.input[0] in local:
                perm = None
                for a in n.attribute:
                    if a.name == 'perm':
                        perm = list(a.ints)
                transposes[n.output[0]] = (n.input[0], perm, n)
        used_outputs = set()
        for n in graph.node:
            if n.op_type != 'MatMul' or len(n.input) != 2:
                continue
            b = n.input[1]
            if b not in transposes:
                continue
            src_name, perm, _tnode = transposes[b]
            key = (src_name, tuple(perm) if perm is not None else None)
            if key not in added:
                arr = numpy_helper.to_array(local[src_name])
                arrT = np.transpose(arr, perm) if perm is not None else np.transpose(arr)
                new_name = f'{src_name}__T_folded'
                top.initializer.append(numpy_helper.from_array(np.ascontiguousarray(arrT), new_name))
                added[key] = new_name
                print(f'fold: {src_name} {arr.shape} -> {new_name} {arrT.shape} perm={perm}')
            n.input[1] = added[key]
            used_outputs.add(b)
            folded += 1
        # 誰も読まなくなった Transpose を外す(同じ出力を別の node が読むなら残す)
        for out, (_s, _p, tnode) in transposes.items():
            if out in used_outputs:
                still = any(out in m.input for m in graph.node) or any(o.name == out for o in graph.output)
                if not still:
                    graph.node.remove(tnode)
        for n in graph.node:
            for a in n.attribute:
                if a.type == onnx.AttributeProto.GRAPH:
                    walk(a.g, local)
                elif a.type == onnx.AttributeProto.GRAPHS:
                    for g in a.graphs:
                        walk(g, local)

    walk(top, {})
    if folded == 0:
        print('::error::畳める MatMul(x, Transpose(initializer)) が 1 件も無い ── 前提(proj_out の形)が崩れている', file=sys.stderr)
        return 2
    onnx.save(model, dst, save_as_external_data=False)
    print(f'folded MatMul inputs: {folded}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
