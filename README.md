# mdx2midi

X68000のMDXフォーマットをMIDIに変換するプログラムを作成します。MDXは、X68000向けのサウンドフォーマットで、MIDIに変換することで他のプラットフォームでも再生可能になります。

このプログラムは、X68000のMDXフォーマットの音楽ファイルをMIDIフォーマットに変換するPythonスクリプトです。プログラムの主な機能は以下の通りです：

1. MDXファイルのヘッダー情報を解析し、曲名やトラック数を取得
2. 各トラックのデータを解析し、ノート、休符、テンポ、音量、音色などのイベントをMIDIイベントに変換
3. 変換したデータをMIDIファイルとして保存

使用方法：
```
python mdx_to_midi.py 入力MDXファイル [-o 出力MIDIファイル]
```

注意点として、このプログラムは基本的なMDXからMIDIへの変換機能を実装していますが、X68000のMDXフォーマットには複雑な機能（エンベロープ、LFO、FMシンセシス固有のパラメータなど）が多くあり、実際の使用ではさらに拡張が必要になるかもしれません。

このプログラムを実行するには、Python環境と`midiutil`パッケージのインストールが必要です：
```
pip install midiutil
```
