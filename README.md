# mdx2midi

X68000のMDXフォーマットをMIDIに変換するプログラムを作成します。MDXは、X68000向けのサウンドフォーマットで、MIDIに変換することで他のプラットフォームでも再生可能になります。

このプログラムは、X68000のMDXフォーマットの音楽ファイルをMIDIフォーマットに変換するPythonスクリプトです。プログラムの主な機能は以下の通りです：

1. MDXファイルのヘッダー情報を解析し、曲名やトラック数を取得
2. 各トラックのデータを解析し、ノート、休符、テンポ、音量、音色などのイベントをMIDIイベントに変換
3. 変換したデータをMIDIファイルとして保存
4. ループ処理の完全実装（ループ回数の制限設定可能）
5. より多くのMDXコマンドのサポート（デチューン、パンポット、ゲートタイム、LFOなど）
6. 堅牢なエラー処理とファイル検証
7. 強制モードによる非標準フォーマットのMDXファイルへの対応

## 使用方法

```
python mdx_to_midi.py 入力MDXファイル [-o 出力MIDIファイル] [-l ループ回数] [-v] [-f]
```

### オプション

- `-o, --output`: 出力MIDIファイル名（デフォルトは入力ファイル名.mid）
- `-l, --loops`: ループの最大繰り返し回数（0=ループなし、デフォルト=2）
- `-v, --verbose`: 詳細なログ出力を有効にする
- `-f, --force`: 強制モード（非標準フォーマットのMDXファイルに対応）

## 強制モード

強制モード（`-f`オプション）は、標準的でないMDXフォーマットや異常なヘッダー値を持つファイルの変換を試みます。このモードでは以下の機能が有効になります：

- 異常なポインタ値の許容
- 無効なトラック数の自動調整
- ファイル内容からの有効なトラックデータの探索
- 文字コード変換エラーの許容

非標準のMDXファイルや破損したファイルを変換する場合に使用してください。

## 対応コマンド

以下のMDXコマンドに対応しています：

- ノートオン (0x80-0xDF)
- 休符 (0x00)
- テンポ設定 (0xE7)
- 音量設定 (0xEB)
- 音色設定 (0xE6)
- ループ開始/終了 (0xE1/0xE2)
- デチューン (0xEA)
- パンポット設定 (0xEC)
- ゲートタイム (0xE9)
- LFO設定（ビブラート、トレモロ、ハードウェアLFO）(0xE3)
- LFO有効化/無効化 (0xE4/0xE5/0xF0/0xF1)
- LFOディレイ設定 (0xEE)
- キーオンディレイ (0xEF)
- ポルタメント (0xE8)
- OPMレジスタ設定（パンポット、フィードバック、微分音程など）(0xED)

## テスト

ユニットテストを実行するには：

```
python test_mdx_to_midi.py
```

## 注意点

このプログラムは基本的なMDXからMIDIへの変換機能を実装していますが、X68000のMDXフォーマットには複雑な機能（エンベロープ、LFO、FMシンセシス固有のパラメータなど）が多くあり、完全な変換は難しい場合があります。特にOPM（YM2151）の音色パラメータはMIDIに完全に対応するものがないため、近似的な変換を行っています。

## 依存パッケージ

このプログラムを実行するには、Python環境と`midiutil`パッケージのインストールが必要です：
```
pip install midiutil
```

## エラー処理

以下のエラーを検出して適切に処理します：

- ファイルが見つからない
- MDXフォーマットが無効
- トラックデータが不完全
- 無効なポインタ値
- バッファ境界外のアクセス
- 文字コード変換エラー
