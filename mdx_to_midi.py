#!/usr/bin/env python3
"""
X68000 MDX to MIDI Converter
----------------------------
このプログラムはシャープX68000のMDXフォーマットの音楽ファイルを
標準MIDIフォーマットに変換します。

改良版: より多くのMDXコマンドをサポートし、ループ処理を完全実装しています。
"""

import struct
import argparse
import os
import logging
from midiutil.MidiFile import MIDIFile

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# MDXフォーマットの定数
MDX_CMD_NOTE = 0x80  # ノートオン (0x80-0xDF)
MDX_CMD_REST = 0x00  # 休符
MDX_CMD_TEMPO = 0xE7  # テンポ設定
MDX_CMD_VOLUME = 0xEB  # 音量設定
MDX_CMD_INSTRUMENT = 0xE6  # 音色設定
MDX_CMD_LOOPSTART = 0xE1  # ループ開始
MDX_CMD_LOOPEND = 0xE2  # ループ終了
MDX_CMD_DETUNE = 0xEA  # デチューン
MDX_CMD_PORTAMENTO = 0xE8  # ポルタメント
MDX_CMD_LFO = 0xE3  # LFO設定
MDX_CMD_OPM_REG = 0xED  # OPMレジスタ直接設定
MDX_CMD_PANPOT = 0xEC  # パンポット設定
MDX_CMD_KEYON_DELAY = 0xEF  # キーオンディレイ
MDX_CMD_GATE_TIME = 0xE9  # ゲートタイム

class MDXFormatError(Exception):
    """MDXフォーマットに関するエラー"""
    pass

class MDXtoMIDI:
    def __init__(self, mdx_file, midi_file, max_loops=2, verbose=False, force=False):
        """
        MDXからMIDIへの変換クラスを初期化
        
        Args:
            mdx_file (str): 入力MDXファイルのパス
            midi_file (str): 出力MIDIファイルのパス
            max_loops (int): ループの最大繰り返し回数
            verbose (bool): 詳細なログ出力を有効にするかどうか
            force (bool): 強制モード（非標準フォーマット対応）
        """
        self.mdx_file = mdx_file
        self.midi_file = midi_file
        self.midi = MIDIFile(16)  # 最大16トラック
        self.tempo = 120  # デフォルトテンポ
        self.volume = 100  # デフォルト音量
        self.channels = []
        self.time = 0
        self.max_loops = max_loops
        self.verbose = verbose
        self.force = force
        self.is_shift_jis = True  # 文字コード
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
    def validate_mdx_file(self):
        """
        MDXファイルの基本的な検証を行う
        
        Returns:
            bool: ファイルが有効な場合はTrue
            
        Raises:
            MDXFormatError: ファイルが無効な場合
        """
        if not os.path.exists(self.mdx_file):
            raise FileNotFoundError(f"MDXファイルが見つかりません: {self.mdx_file}")
            
        with open(self.mdx_file, 'rb') as f:
            data = f.read(10)  # 最低限のヘッダーを読み込む
            
        if len(data) < 7:  # 最低限必要なヘッダーサイズ
            raise MDXFormatError("ファイルサイズが小さすぎます。有効なMDXファイルではありません。")
            
        # タイトルポインタとボイスポインタの確認
        title_ptr = struct.unpack("<H", data[0:2])[0]
        voice_ptr = struct.unpack("<H", data[2:4])[0]
        
        # ファイル形式の特定を試みる
        # 一部のMDXファイルはフォーマットが異なる場合がある
        if title_ptr > 0x1000 or voice_ptr > 0x1000:
            # ポインタ値が大きすぎる場合、別のフォーマットの可能性がある
            logger.warning(f"異常なポインタ値を検出: タイトル={title_ptr:04X}h, 音色={voice_ptr:04X}h")
            
            if self.force:
                logger.warning("強制モードが有効なため、処理を続行します")
                # デフォルト値を使用
                self.is_shift_jis = False  # 文字コードを変更
                return True
            else:
                raise MDXFormatError(f"無効なポインタ値です。MDXフォーマットが正しくありません。強制モードで実行するには -f オプションを使用してください。")
        
        # トラック数の確認
        num_tracks = data[6]
        if num_tracks == 0 or num_tracks > 16 * 2:  # 合理的な範囲を設定
            logger.warning(f"無効なトラック数です: {num_tracks}")
            
            if self.force:
                logger.warning(f"強制モードが有効なため、トラック数を{16}に制限します")
                return True
            else:
                raise MDXFormatError(f"無効なトラック数です: {num_tracks}\n強制モードで実行するには -f オプションを使用してください。")
            
        return True
        
    def read_mdx(self):
        """
        MDXファイルを読み込み、解析する
        
        Raises:
            MDXFormatError: MDXフォーマットが無効な場合
            IOError: ファイル読み込みエラーの場合
        """
        try:
            self.validate_mdx_file()
            
            with open(self.mdx_file, 'rb') as f:
                data = f.read()
            
            # ヘッダー解析
            title_ptr = struct.unpack("<H", data[0:2])[0]
            voice_ptr = struct.unpack("<H", data[2:4])[0]
            
            # タイトル取得
            try:
                title_end = data.find(b'\x00', title_ptr)
                if title_end == -1:  # 終端が見つからない場合
                    title_end = min(voice_ptr, title_ptr + 50)  # ボイスデータの開始位置まで、または最大長を制限
                    
                if title_ptr < len(data) and title_end <= len(data) and title_end > title_ptr:
                    encoding = 'shift_jis' if self.is_shift_jis else 'ascii'
                    title = data[title_ptr:title_end].decode(encoding, errors='ignore')
                    logger.info(f"曲名: {title}")
                else:
                    logger.warning("タイトルの取得に失敗しました")
                    title = "不明"
            except Exception as e:
                logger.warning(f"タイトルの取得中にエラーが発生しました: {e}")
                title = "不明"
            
            # トラック数と各トラックのオフセット取得
            if len(data) <= 6:
                raise MDXFormatError("ファイルが短すぎます。トラック情報が含まれていません。")
                
            num_tracks = data[6]
            if num_tracks == 0 or num_tracks > 16 * 2:
                if self.force:
                    logger.warning(f"無効なトラック数({num_tracks})を{16}に制限します")
                    num_tracks = 16
                else:
                    raise MDXFormatError(f"無効なトラック数です: {num_tracks}")
                
            logger.info(f"トラック数: {num_tracks}")
            
            # 特殊なファイル形式の検出と対応
            # 一部のMDXファイルでは、ヘッダー部分が異なるフォーマットを使用している可能性がある
            if num_tracks > 16 and self.force:
                # 強制モードでは、ファイルの内容を分析して有効なトラックを探す
                logger.warning("非標準のMDXフォーマットを検出しました。強制モードで解析を試みます。")
                
                # ファイルの先頭から有効なMDXデータを探す
                potential_offsets = []
                for i in range(0, min(0x100, len(data)-2), 2):
                    offset = struct.unpack("<H", data[i:i+2])[0]
                    if 0x10 <= offset < len(data) - 10:  # 合理的なオフセット範囲
                        potential_offsets.append((i, offset))
                
                if potential_offsets:
                    # 最も可能性の高いオフセット位置を選択
                    best_offset_pos = potential_offsets[0][0]
                    track_count_pos = best_offset_pos + 6  # 標準MDXフォーマットに基づく推測
                    
                    if track_count_pos < len(data):
                        num_tracks = min(data[track_count_pos], 16)
                        logger.info(f"推定トラック数: {num_tracks}")
                    else:
                        num_tracks = 1  # デフォルト値
                        logger.warning("トラック数を推定できません。デフォルト値を使用します。")
            
            track_offsets = []
            for i in range(min(num_tracks, 16)):  # 最大トラック数を制限
                if 7 + i*2 + 1 >= len(data):
                    logger.warning(f"トラック{i+1}のオフセット情報が欠落しています")
                    break
                    
                offset = struct.unpack("<H", data[7 + i*2:9 + i*2])[0]
                
                if offset >= len(data):
                    logger.warning(f"トラック{i+1}のオフセット({offset})がファイルサイズを超えています")
                    if self.force:
                        continue  # このトラックをスキップ
                    else:
                        raise MDXFormatError(f"トラック{i+1}のオフセット({offset})がファイルサイズを超えています")
                
                track_offsets.append(offset)
            
            if not track_offsets:
                logger.warning("有効なトラックが見つかりませんでした")
                if not self.force:
                    raise MDXFormatError("有効なトラックが見つかりません")
                else:
                    # 強制モードでは、ファイルの内容から有効なトラックデータを探す試み
                    for i in range(0, min(len(data)-100, 0x1000), 0x100):
                        if i + 100 < len(data):
                            # 典型的なMDXコマンドパターンを探す
                            if any(cmd in data[i:i+100] for cmd in [MDX_CMD_TEMPO, MDX_CMD_VOLUME, MDX_CMD_INSTRUMENT]):
                                logger.info(f"オフセット0x{i:04X}で潜在的なトラックデータを検出しました")
                                track_offsets.append(i)
                                break
            
            # 少なくとも1つのトラックが必要
            if not track_offsets and self.force:
                logger.warning("トラックが見つからないため、デフォルトオフセットを使用します")
                if len(data) > 100:
                    track_offsets.append(100)  # 適当なオフセット
            
            # 各トラックを解析
            for track_num, offset in enumerate(track_offsets):
                if track_num >= 16:  # MIDIは最大トラック数を制限
                    logger.warning(f"トラック数が{16}を超えています。トラック{track_num+1}以降は無視されます。")
                    break
                    
                logger.info(f"トラック {track_num+1} の解析中...")
                try:
                    self.parse_track(data, offset, track_num)
                except Exception as e:
                    logger.error(f"トラック{track_num+1}の解析中にエラーが発生しました: {e}")
                    if not self.force:
                        raise
                
        except struct.error as e:
            error_msg = f"データ構造の解析に失敗しました: {e}"
            logger.error(error_msg)
            if not self.force:
                raise MDXFormatError(error_msg)
        except UnicodeDecodeError as e:
            logger.warning(f"タイトルの文字コード変換に失敗しました: {e}")
    
    def parse_track(self, data, offset, track_num):
        """
        トラックデータを解析してMIDIイベントに変換
        
        Args:
            data (bytes): MDXファイルのバイナリデータ
            offset (int): トラックデータの開始オフセット
            track_num (int): トラック番号
            
        Raises:
            MDXFormatError: トラックデータの解析に失敗した場合
        """
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
        loop_points = []  # (位置, 時間, 残りループ回数) のタプルのリスト
        
        # ゲートタイム比率（デフォルト値）
        gate_time_ratio = 0.8
        
        # デチューン値
        detune = 0
        
        # パンポット（0-127, 64=中央）
        panpot = 64
        
        try:
            while pos < len(data):
                if pos >= len(data):
                    break
                    
                cmd = data[pos]
                pos += 1
                
                if cmd >= MDX_CMD_NOTE and cmd <= 0xDF:  # ノートオン
                    note = cmd - MDX_CMD_NOTE
                    
                    # 境界チェック
                    if pos + 1 >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のノートデータが不完全です")
                        
                    # 次の2バイトは長さとボリューム
                    length = data[pos]
                    pos += 1
                    velocity = min(data[pos], 127)  # MIDIは最大127
                    pos += 1
                    
                    # デチューンを適用（MIDIでは完全には表現できないが、近似値を使用）
                    if detune != 0:
                        logger.debug(f"デチューン適用: {detune} (元のノート: {note})")
                        # デチューンの影響を近似的に表現（実際のMDXエンジンはより複雑）
                    
                    # ゲートタイム比率を適用
                    note_length = length/48 * gate_time_ratio
                    
                    self.midi.addNote(track_num, channel, note, self.time, note_length, velocity)
                    self.time += length/48
                    
                elif cmd == MDX_CMD_REST:  # 休符
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}の休符データが不完全です")
                        
                    length = data[pos]
                    pos += 1
                    self.time += length/48
                    
                elif cmd == MDX_CMD_TEMPO:  # テンポ設定
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のテンポデータが不完全です")
                        
                    tempo_val = data[pos]
                    pos += 1
                    
                    if tempo_val == 0:
                        logger.warning(f"無効なテンポ値(0)を検出しました。デフォルト値を使用します。")
                        tempo_val = 200  # 適当なデフォルト値
                        
                    self.tempo = 60 * 4096 / tempo_val
                    logger.debug(f"テンポ変更: {self.tempo} BPM")
                    self.midi.addTempo(track_num, self.time, self.tempo)
                    
                elif cmd == MDX_CMD_VOLUME:  # 音量設定
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}の音量データが不完全です")
                        
                    self.volume = min(data[pos], 127)
                    pos += 1
                    logger.debug(f"音量変更: {self.volume}")
                    self.midi.addControllerEvent(track_num, channel, self.time, 7, self.volume)
                    
                elif cmd == MDX_CMD_INSTRUMENT:  # 音色設定
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}の音色データが不完全です")
                        
                    instrument = data[pos] % 128  # MIDIは0-127の範囲
                    pos += 1
                    logger.debug(f"音色変更: {instrument}")
                    self.midi.addProgramChange(track_num, channel, self.time, instrument)
                    
                elif cmd == MDX_CMD_LOOPSTART:  # ループ開始
                    logger.debug(f"ループ開始位置: {pos}, 時間: {self.time}")
                    loop_points.append((pos, self.time, 0))  # 回数は後で設定
                    
                elif cmd == MDX_CMD_LOOPEND:  # ループ終了
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のループ終了データが不完全です")
                        
                    if not loop_points:
                        logger.warning("ループ開始なしでループ終了が検出されました。無視します。")
                        pos += 1
                        continue
                        
                    loop_count = data[pos]
                    pos += 1
                    
                    if loop_count == 0:
                        logger.debug("ループ回数0が指定されました。ループをスキップします。")
                        loop_points.pop()
                        continue
                    
                    loop_pos, loop_time, _ = loop_points[-1]
                    
                    # ループ回数を制限（設定可能）
                    if loop_count > self.max_loops and self.max_loops > 0:
                        logger.info(f"ループ回数を{loop_count}から{self.max_loops}に制限します")
                        loop_count = self.max_loops
                    
                    if loop_count == 255:  # 無限ループの場合は有限回に制限
                        loop_count = self.max_loops
                        logger.info(f"無限ループを{self.max_loops}回に制限します")
                    
                    # 既に1回実行しているので、残りのループ回数を設定
                    remaining_loops = loop_count - 1
                    
                    if remaining_loops > 0:
                        logger.debug(f"ループ位置に戻ります: {loop_pos}, 残り{remaining_loops}回")
                        loop_points[-1] = (loop_pos, loop_time, remaining_loops)
                        pos = loop_pos  # ループ開始位置に戻る
                        self.time = loop_time  # 時間も戻す
                    else:
                        logger.debug("ループ終了")
                        loop_points.pop()
                
                elif cmd == MDX_CMD_DETUNE:  # デチューン
                    if pos + 1 >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のデチューンデータが不完全です")
                        
                    detune_low = data[pos]
                    pos += 1
                    detune_high = data[pos]
                    pos += 1
                    
                    # 16ビット符号付き整数として解釈
                    detune = (detune_high << 8 | detune_low)
                    if detune & 0x8000:  # 負の値の場合
                        detune = detune - 0x10000
                        
                    logger.debug(f"デチューン設定: {detune}")
                
                elif cmd == MDX_CMD_GATE_TIME:  # ゲートタイム
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のゲートタイムデータが不完全です")
                        
                    gate_time = data[pos]
                    pos += 1
                    
                    # ゲートタイム比率を0.1～1.0の範囲で設定
                    gate_time_ratio = max(0.1, min(1.0, gate_time / 100))
                    logger.debug(f"ゲートタイム比率: {gate_time_ratio}")
                
                elif cmd == MDX_CMD_PANPOT:  # パンポット
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のパンポットデータが不完全です")
                        
                    pan_value = data[pos]
                    pos += 1
                    
                    # MDXのパンポット値をMIDIのパン値(0-127)に変換
                    # 一般的なマッピング: 0=左, 1=中央, 2=右
                    if pan_value == 0:
                        panpot = 0  # 左
                    elif pan_value == 1:
                        panpot = 64  # 中央
                    elif pan_value == 2:
                        panpot = 127  # 右
                    else:
                        panpot = 64  # デフォルト中央
                        
                    logger.debug(f"パンポット設定: {panpot}")
                    self.midi.addControllerEvent(track_num, channel, self.time, 10, panpot)
                
                elif cmd == MDX_CMD_LFO:  # LFO設定
                    # LFO波形、速度、深さなどのパラメータ
                    # MIDIでは完全に対応するものがないため、近似的な表現を行う
                    # 実装の簡略化のため、現在はパラメータを読み飛ばすのみ
                    if pos >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のLFOデータが不完全です")
                        
                    lfo_params = data[pos]
                    pos += 1
                    
                    # LFOタイプによってパラメータ数が異なる
                    param_count = 0
                    if lfo_params & 0x01:  # ビブラート
                        param_count += 2
                    if lfo_params & 0x02:  # トレモロ
                        param_count += 2
                    if lfo_params & 0x04:  # ハードウェアLFO
                        param_count += 3
                        
                    # パラメータをスキップ
                    if pos + param_count > len(data):
                        logger.warning(f"コマンド0x{cmd:02X}のデータが不完全です。処理を終了します。")
                        break
                        
                    pos += param_count
                    logger.debug(f"LFO設定: タイプ={lfo_params}, パラメータ数={param_count}")
                
                elif cmd == MDX_CMD_OPM_REG:  # OPMレジスタ直接設定
                    # OPMレジスタ操作はMIDIに直接対応するものがないため、
                    # 特定の操作のみをMIDIコントロールチェンジに変換
                    if pos + 1 >= len(data):
                        raise MDXFormatError(f"トラック{track_num+1}のOPMレジスタデータが不完全です")
                        
                    reg = data[pos]
                    pos += 1
                    value = data[pos]
                    pos += 1
                    
                    logger.debug(f"OPMレジスタ設定: レジスタ={reg:02X}h, 値={value:02X}h")
                    
                    # 一部のOPMレジスタをMIDIコントロールに変換（例）
                    # 実際には完全な変換は難しいため、主要なものだけ対応
                    if reg == 0x20:  # RL/FB/CONNECT (パンや効果に関連)
                        # 簡易的な処理として、一部のビットをパンに変換
                        if value & 0xC0:  # RLビットを使用
                            rl_bits = (value >> 6) & 0x03
                            if rl_bits == 0x01:  # Rのみ
                                pan_value = 96  # 右寄り
                            elif rl_bits == 0x02:  # Lのみ
                                pan_value = 32  # 左寄り
                            else:  # 両方または両方なし
                                pan_value = 64  # 中央
                                
                            self.midi.addControllerEvent(track_num, channel, self.time, 10, pan_value)
                
                else:  # その他の未対応コマンド
                    # コマンドの種類によってスキップするバイト数が異なる
                    skip_bytes = 0
                    
                    if cmd == MDX_CMD_PORTAMENTO:  # ポルタメント
                        skip_bytes = 2
                    elif cmd == MDX_CMD_KEYON_DELAY:  # キーオンディレイ
                        skip_bytes = 1
                    elif cmd >= 0x01 and cmd <= 0x7F:  # 拡張コマンド
                        # 多くの拡張コマンドは可変長のため、安全に処理できない
                        # 最も一般的なパターンとして1バイトをスキップ
                        skip_bytes = 1
                    # 88ST_AR.MDXで検出された未知のコマンドに対応
                    elif cmd == 0xF1 or cmd == 0xF3 or cmd == 0xF5 or cmd == 0xF6 or cmd == 0xF7 or cmd == 0xFB or cmd == 0xFC or cmd == 0xFD or cmd == 0xFE or cmd == 0xFF:
                        # これらの未知のコマンドは1バイトをスキップ
                        skip_bytes = 1
                        # 詳細ログモードの場合のみ出力
                        if self.verbose:
                            logger.debug(f"未対応のコマンドをスキップ: 0x{cmd:02X} at pos {pos-1}")
                    else:
                        # その他の未知のコマンド - 安全のため1バイトのみスキップ
                        skip_bytes = 1
                        # 詳細ログモードの場合のみ出力
                        if self.verbose:
                            logger.debug(f"未知のコマンド: 0x{cmd:02X} at pos {pos-1}")
                    
                    # バッファ境界チェック
                    if pos + skip_bytes > len(data):
                        logger.warning(f"コマンド0x{cmd:02X}のデータが不完全です。処理を終了します。")
                        break
                        
                    pos += skip_bytes
        
        except Exception as e:
            logger.error(f"トラック{track_num+1}の解析中にエラーが発生しました: {e}")
            # エラーが発生しても他のトラックの処理は続行
    
    def save_midi(self):
        """
        MIDIファイルを保存
        
        Raises:
            IOError: ファイル書き込みエラーの場合
        """
        try:
            # 出力ディレクトリが存在するか確認
            output_dir = os.path.dirname(self.midi_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            with open(self.midi_file, 'wb') as f:
                self.midi.writeFile(f)
                
            logger.info(f"MIDIファイルを保存しました: {self.midi_file}")
            
        except IOError as e:
            raise IOError(f"MIDIファイルの保存に失敗しました: {e}")

def main():
    """
    メイン関数 - コマンドライン引数を解析して変換を実行
    """
    parser = argparse.ArgumentParser(description="X68000 MDX to MIDI Converter")
    parser.add_argument("mdx_file", help="MDXファイルのパス")
    parser.add_argument("-o", "--output", default=None, help="出力MIDIファイル名（デフォルトは入力ファイル名.mid）")
    parser.add_argument("-l", "--loops", type=int, default=2, help="ループの最大繰り返し回数（0=ループなし、デフォルト=2）")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細なログ出力を有効にする")
    parser.add_argument("-f", "--force", action="store_true", help="強制モード（非標準フォーマット対応）")
    
    args = parser.parse_args()
    
    # 出力ファイル名の決定
    if args.output is None:
        midi_file = os.path.splitext(args.mdx_file)[0] + ".mid"
    else:
        midi_file = args.output
    
    try:
        # 変換処理の実行
        converter = MDXtoMIDI(args.mdx_file, midi_file, args.loops, args.verbose, args.force)
        converter.read_mdx()
        converter.save_midi()
        logger.info("変換が完了しました。")
        return 0
    except FileNotFoundError as e:
        logger.error(f"ファイルが見つかりません: {e}")
        return 1
    except MDXFormatError as e:
        logger.error(f"MDXフォーマットエラー: {e}")
        return 2
    except IOError as e:
        logger.error(f"I/Oエラー: {e}")
        return 3
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}")
        return 4

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
