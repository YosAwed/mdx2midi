#!/usr/bin/env python3
"""
X68000 MDX to MIDI Converter
----------------------------
このプログラムはシャープX68000のMDXフォーマットの音楽ファイルを
標準MIDIフォーマットに変換します。
"""

import struct
import argparse
from midiutil.MidiFile import MIDIFile

# MDXフォーマットの定数
MDX_CMD_NOTE = 0x80  # ノートオン
MDX_CMD_REST = 0x00  # 休符
MDX_CMD_TEMPO = 0xE7  # テンポ設定
MDX_CMD_VOLUME = 0xEB  # 音量設定
MDX_CMD_INSTRUMENT = 0xE6  # 音色設定
MDX_CMD_LOOPSTART = 0xE1  # ループ開始
MDX_CMD_LOOPEND = 0xE2  # ループ終了

class MDXtoMIDI:
    def __init__(self, mdx_file, midi_file):
        self.mdx_file = mdx_file
        self.midi_file = midi_file
        self.midi = MIDIFile(16)  # 最大16トラック
        self.tempo = 120  # デフォルトテンポ
        self.volume = 100  # デフォルト音量
        self.channels = []
        self.time = 0
        
    def read_mdx(self):
        """MDXファイルを読み込む"""
        with open(self.mdx_file, 'rb') as f:
            data = f.read()
        
        # ヘッダー解析
        title_ptr = struct.unpack("<H", data[0:2])[0]
        voice_ptr = struct.unpack("<H", data[2:4])[0]
        
        # タイトル取得（必要に応じて）
        title_end = data.find(b'\x00', title_ptr)
        title = data[title_ptr:title_end].decode('shift-jis', errors='ignore')
        print(f"曲名: {title}")
        
        # トラック数と各トラックのオフセット取得
        num_tracks = struct.unpack("<B", data[6:7])[0]
        print(f"トラック数: {num_tracks}")
        
        track_offsets = []
        for i in range(num_tracks):
            offset = struct.unpack("<H", data[7 + i*2:9 + i*2])[0]
            track_offsets.append(offset)
        
        # 各トラックを解析
        for track_num, offset in enumerate(track_offsets):
            if track_num >= 16:  # MIDIは最大16トラック
                break
                
            print(f"トラック {track_num+1} の解析中...")
            self.parse_track(data, offset, track_num)
    
    def parse_track(self, data, offset, track_num):
        """トラックデータを解析してMIDIイベントに変換"""
        # トラック情報の初期化
        self.midi.addTrackName(track_num, 0, f"Track {track_num+1}")
        self.midi.addTempo(track_num, 0, self.tempo)
        
        channel = track_num % 16
        self.channels.append(channel)
        
        # デフォルト楽器を設定（GM音源の場合）
        instrument = 0  # GM音源のピアノ
        self.midi.addProgramChange(track_num, channel, 0, instrument)
        
        pos = offset
        self.time = 0
        loop_points = []
        
        while pos < len(data):
            cmd = data[pos]
            pos += 1
            
            if cmd >= MDX_CMD_NOTE:  # ノートオン
                note = cmd - MDX_CMD_NOTE
                # 次の2バイトは長さとボリューム
                length = data[pos]
                pos += 1
                velocity = min(data[pos], 127)  # MIDIは最大127
                pos += 1
                
                self.midi.addNote(track_num, channel, note, self.time, length/48, velocity)
                self.time += length/48
                
            elif cmd == MDX_CMD_REST:  # 休符
                length = data[pos]
                pos += 1
                self.time += length/48
                
            elif cmd == MDX_CMD_TEMPO:  # テンポ設定
                tempo_val = data[pos]
                pos += 1
                self.tempo = 60 * 4096 / tempo_val
                self.midi.addTempo(track_num, self.time, self.tempo)
                
            elif cmd == MDX_CMD_VOLUME:  # 音量設定
                self.volume = min(data[pos], 127)
                pos += 1
                self.midi.addControllerEvent(track_num, channel, self.time, 7, self.volume)
                
            elif cmd == MDX_CMD_INSTRUMENT:  # 音色設定
                instrument = data[pos] % 128  # MIDIは0-127の範囲
                pos += 1
                self.midi.addProgramChange(track_num, channel, self.time, instrument)
                
            elif cmd == MDX_CMD_LOOPSTART:  # ループ開始
                loop_points.append((pos, self.time))
                
            elif cmd == MDX_CMD_LOOPEND:  # ループ終了
                if loop_points:
                    loop_count = data[pos]
                    pos += 1
                    
                    if loop_count > 0:
                        loop_pos, loop_time = loop_points[-1]
                        # 実装簡略化のため、ループは2回まで
                        if loop_count > 2:
                            loop_count = 2
                            
                        for _ in range(loop_count - 1):
                            # ループ部分を再度処理（簡易的な実装）
                            # 実際のMDXエンジンはもっと複雑
                            pass
                            
                    loop_points.pop()
                    
            else:  # その他のコマンド（簡略化のため無視）
                # MDXには多くのコマンドがあり、実際の実装ではすべてサポートする必要がある
                pos += 1
    
    def save_midi(self):
        """MIDIファイルを保存"""
        with open(self.midi_file, 'wb') as f:
            self.midi.writeFile(f)
        print(f"MIDIファイルを保存しました: {self.midi_file}")

def main():
    parser = argparse.ArgumentParser(description="X68000 MDX to MIDI Converter")
    parser.add_argument("mdx_file", help="MDXファイルのパス")
    parser.add_argument("-o", "--output", default=None, help="出力MIDIファイル名（デフォルトは入力ファイル名.mid）")
    
    args = parser.parse_args()
    
    if args.output is None:
        midi_file = args.mdx_file.rsplit('.', 1)[0] + ".mid"
    else:
        midi_file = args.output
    
    converter = MDXtoMIDI(args.mdx_file, midi_file)
    try:
        converter.read_mdx()
        converter.save_midi()
        print("変換が完了しました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    main()
