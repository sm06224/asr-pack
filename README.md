# asr-pack

**PKC3 の「音声・動画を文字にする」が端末へ取り込む部品一式(音声認識)を配るだけ**のリポジトリです。
アプリ本体は [sm06224/PKC3](https://github.com/sm06224/PKC3) にあります(issue #772)。

配信先: `https://sm06224.github.io/asr-pack/`(PKC3 の app は同一 origin の `/asr-pack/pack.json` を読む)

## なぜ本体と分けてあるか(office-pack と同じ)

GitHub Pages は同一ユーザーの全リポジトリが `https://<user>.github.io` という同じ origin に載るので、
別リポジトリでも PKC3 本体から見て**同一 origin**で CORS は起きません。そのうえで:

- 更新周期が違う(重みは年に数回 / PKC3 本体は毎日)
- 本体の deploy 時間にも検品(`check-dist`)にも影響しない
- 約 350MB(small の重み 1 file が 157MB)を本体の git 履歴にも deploy artifact にも持ち込まない
- Office の配信(`office-pack`)を asr の不具合で巻き込まない(🟣 Gemini 裁定 2026-10-02: 新 repo)

🔴 **重みは git に入れない。** GitHub Actions の中で上流(`openai/whisper-*`)から ONNX へ変換し、
成果物から直接 Pages へ配る(git で配る Pages の 1 file 100MB の壁を避ける)。

## 何が置かれるか

| path | 中身 |
|---|---|
| `pack.json` | 目録(version は内容由来 / runtime / models.light / models.accurate)。取る側は最初にこれを読む |
| `runtime/transformers.mjs` | transformers.js(web 版)+ onnxruntime-web を 1 枚の ESM に束ねた物 |
| `runtime/ort-wasm.mjs` / `runtime/ort-wasm.wasm` | ONNX Runtime Web の wasm(14.3MB) |
| `models/openai/whisper-base/…` | 軽い(q8。config / tokenizer 一式 + `onnx/*_quantized.onnx`) |
| `models/openai/whisper-small/…` | 当たりやすい(q8) |
| `LICENSES/` | 同梱するライセンス(束ねの閉包 + 上流の全文 + 重みの配布元の宣言 `MODELS.json`) |

🔑 **組み立ての正本は PKC3 に 1 つだけ**(`build/asr-pack/`)。この workflow はそれを checkout して呼ぶだけで、
目録の形も検品もここには書き写しません(`pack.json` の形は PKC3 の `src/features/asr/asr-parts.ts` が決める)。

## 🔴 初回だけ、手で 1 つ入れる設定がある(済み 2026-10-03)

**Settings → Pages → Build and deployment → Source を「GitHub Actions」にする。**
`actions/configure-pages` の `enablement: true` では足りない(office-pack で実測)。

## 回し方(Actions → pages → Run workflow)

| input | 既定 | 何か |
|---|---|---|
| `mode` | `build` | `probe` = 157MB のダミー 1 本だけ配って、公開 URL から落として sha256 を突き合わせる(段 0)/ `build` = 変換して配る |
| `pkc3_ref` | `main` | 組み立て script と目録の正本を取る PKC3 の ref(⚠ `ASR_PARTS` の `modelId` が `openai/whisper-*` である版) |
| `transformersjs_ref` | `3.7.6` | 変換 script(`scripts/convert.py`)を取る transformers.js の ref |

`build` は 3 段: **convert**(base / small を別 job で変換。1 job = 1 主張)→ **assemble**(PKC3 の script で束ね・ライセンス・目録・検品 → deploy)→ **verify**(公開 URL から `pack.json` と全 file を落として大きさと sha256 を突き合わせる)。

⚠ **自動追従はしません**。重みが変わるのは大事なので、明示操作にしてあります。
