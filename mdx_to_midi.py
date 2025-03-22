#!/usr/bin/env python3
"""
X68000 MDX to MIDI Converter - Improved Version
-----------------------------------------------
このプログラムはシャープX68000のMDXフォーマットの音楽ファイルを
標準MIDIフォーマットに変換します。より高精度な変換を実現します。

主な改良点:
- より精密なテンポ変換
- OPMの音色パラメータをより良くGM音源にマッピング
- 詳細なMDXコマンドのサポート（デチューン、LFO、ポルタメントなど）
- 堅牢なエラー処理とファイル検証
- ループ処理の改善
"""

import struct
import argparse
import os
import logging
import math
from midiutil.MidiFile import MIDIFile

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# MDXフォーマットの定数
# 基本コマンド
MDX_CMD_REST = 0x00  # 休符
MDX_CMD_NOTE = 0x80  # ノートオン (0x80-0xDF)

# コントロールコマンド
MDX_CMD_LOOPSTART = 0xE1  # ループ開始
MDX_CMD_LOOPEND = 0xE2  # ループ終了
MDX_CMD_LFO = 0xE3  # LFO設定
MDX_CMD_LFOON_PITCH = 0xE4  # ピッチLFO ON
MDX_CMD_LFOON_VOLUME = 0xE5  # ボリュームLFO ON
MDX_CMD_INSTRUMENT = 0xE6  # 音色設定
MDX_CMD_TEMPO = 0xE7  # テンポ設定
MDX_CMD_PORTAMENTO = 0xE8  # ポルタメント
MDX_CMD_GATE_TIME = 0xE9  # ゲートタイム
MDX_CMD_DETUNE = 0xEA  # デチューン
MDX_CMD_VOLUME = 0xEB  # 音量設定
MDX_CMD_PANPOT = 0xEC  # パンポット設定
MDX_CMD_OPM_REG = 0xED  # OPMレジスタ直接設定
MDX_CMD_LFODELAY = 0xEE  # LFOディレイ設定
MDX_CMD_KEYON_DELAY = 0xEF  # キーオンディレイ
MDX_CMD_LFOFF_PITCH = 0xF0  # ピッチLFO OFF
MDX_CMD_LFOFF_VOLUME = 0xF1  # ボリュームLFO OFF

# 特別なMIDIコントローラー
MIDI_CTRL_BANK_SELECT = 0
MIDI_CTRL_VOLUME = 7
MIDI_CTRL_PAN = 10
MIDI_CTRL_EXPRESSION = 11
MIDI_CTRL_SUSTAIN = 64
MIDI_CTRL_RPN_MSB = 101
MIDI_CTRL_RPN_LSB = 100
MIDI_CTRL_DATA_ENTRY_MSB = 6
MIDI_CTRL_DATA_ENTRY_LSB = 38

# RPN値
RPN_PITCH_BEND_RANGE = (0, 0)

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
        self.channels = []
        self.time = 0
        self.max_loops = max_loops
        self.verbose = verbose
        self.force = force
        self.is_shift_jis = True  # 文字コード
        
        # ボイスマッピング情報
        self.voice_mapping = {}   # OPM音色とGM音色のマッピング
        
        # MDXファイルのデータ
        self.data = None
        
        # 一時的なパラメータ保存用
        self.track_params = {}
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            
    def opm_to_gm_instrument(self, opm_voice):
        """
        OPM音色パラメータをGM音色にマッピング（改良版）
        
        Args:
            opm_voice (int): OPM音色番号
            
        Returns:
            int: GM音色番号(0-127)
        """
        # 既知の音色マッピングがあればそれを使用
        if opm_voice in self.voice_mapping:
            return self.voice_mapping[opm_voice]
        
        # 基本的なマッピング
        # 一般的なOPM音色と近いGM音色とのマッピング
        # これはファイルの分析や音色特性に基づいて改良できる
        
        # デフォルトの音色マップ (OPM_VOICE_NUM -> GM_PROGRAM_NUM)
        default_mapping = {
            0: 0,    # Piano 1
            1: 1,    # Piano 2
            2: 4,    # Electric Piano
            3: 7,    # Harpsichord
            4: 17,   # Organ
            5: 19,   # Church Organ
            6: 25,   # Acoustic Guitar
            7: 26,   # Electric Guitar
            8: 33,   # Acoustic Bass
            9: 34,   # Electric Bass
            10: 41,  # Violin
            11: 42,  # Viola
            12: 57,  # Trumpet
            13: 59,  # Tuba
            14: 66,  # Saxophone
            15: 74,  # Flute
            16: 116, # Taiko Drum
            17: 118, # Synth Drum
            # 以下、音色番号が足りない場合は適宜追加
        }
        
        # 音色番号を0-127の範囲に制限し、マッピングがない場合はデフォルト値を使用
        limited_opm_voice = min(opm_voice, 127)
        gm_voice = default_mapping.get(limited_opm_voice, limited_opm_voice % 128)
        
        # マッピングを保存
        self.voice_mapping[opm_voice] = gm_voice
        
        return gm_voice
        
    def calculate_midi_tempo(self, mdx_tempo):
        """
        MDXテンポ値からMIDIテンポ値を計算する（改良版）
        
        Args:
            mdx_tempo (int): MDXテンポ値 (1-255)
            
        Returns:
            int: MIDI BPM値
        """
        if mdx_tempo == 0:
            logger.warning("テンポ値0が指定されました。デフォルト値(200)を使用します")
            mdx_tempo = 200  # 適切なデフォルト値
            
        # MDXのテンポ計算式に基づく変換（より正確な計算）
        # MDXテンポ → マイクロ秒/四分音符 → BPM
        tempo_usec = 60 * 1000000 / (4096 / mdx_tempo)
        return int(tempo_usec)
        
    def validate_mdx_file(self):
        """
        MDXファイルの基本的な検証を行う（改良版）
        
        Returns:
            bool: ファイルが有効な場合はTrue
            
        Raises:
            MDXFormatError: ファイルが無効な場合
            FileNotFoundError: ファイルが存在しない場合
        """
        if not os.path.exists(self.mdx_file):
            raise FileNotFoundError(f"MDXファイルが見つかりません: {self.mdx_file}")
            
        try:
            with open(self.mdx_file, 'rb') as f:
                data = f.read(16)  # より多くのヘッダー情報を読み込む
                
            # ファイルサイズの確認
            if len(data) < 7:  # 最低限必要なヘッダーサイズ
                raise MDXFormatError("ファイルサイズが小さすぎます。有効なMDXファイルではありません。")
                
            # タイトルポインタとボイスポインタの確認
            title_ptr = struct.unpack("<H", data[0:2])[0]
            voice_ptr = struct.unpack("<H", data[2:4])[0]
            
            # ポインタ値の妥当性確認（改良版）
            file_size = os.path.getsize(self.mdx_file)
            
            # ポインタ値が小さすぎる場合もエラーとする
            min_valid_ptr = 7 + (2 * data[6])  # ヘッダーサイズ + トラックポインタサイズ
            
            if title_ptr < min_valid_ptr or voice_ptr < min_valid_ptr:
                logger.warning(f"ポインタ値が小さすぎます: タイトル={title_ptr:04X}h, 音色={voice_ptr:04X}h")
                if not self.force:
                    raise MDXFormatError("ポインタ値が小さすぎます。有効なMDXファイルではありません。")
            
            if title_ptr > file_size or voice_ptr > file_size:
                logger.warning(f"ポインタがファイルサイズを超えています: タイトル={title_ptr:04X}h, 音色={voice_ptr:04X}h")
                if not self.force:
                    raise MDXFormatError("ポインタ値がファイルサイズを超えています")
            
            # トラック数の確認（改良版）
            num_tracks = data[6]
            if num_tracks == 0 or num_tracks > 16 * 2:  # 合理的な範囲を設定
                logger.warning(f"無効なトラック数です: {num_tracks}")
                
                if self.force:
                    logger.warning(f"強制モードが有効なため、トラック数を{16}に制限します")
                else:
                    raise MDXFormatError(f"無効なトラック数です: {num_tracks}\n強制モードで実行するには -f オプションを使用してください。")
                
            return True
            
        except (IOError, struct.error) as e:
            raise MDXFormatError(f"ファイル検証中にエラーが発生しました: {e}")
        
    def read_mdx(self):
        """
        MDXファイルを読み込み、解析する（改良版）
        
        Raises:
            MDXFormatError: MDXフォーマットが無効な場合
            IOError: ファイル読み込みエラーの場合
        """
        try:
            self.validate_mdx_file()
            
            with open(self.mdx_file, 'rb') as f:
                self.data = f.read()
            
            # ヘッダー解析
            title_ptr = struct.unpack("<H", self.data[0:2])[0]
            voice_ptr = struct.unpack("<H", self.data[2:4])[0]
            
            # タイトル取得（改良版）
            try:
                title_end = self.data.find(b'\x00', title_ptr)
                if title_end == -1:  # 終端が見つからない場合
                    title_end = min(voice_ptr, title_ptr + 50)  # ボイスデータの開始位置まで、または最大長を制限
                    
                if title_ptr < len(self.data) and title_end <= len(self.data) and title_end > title_ptr:
                    encoding = 'shift_jis' if self.is_shift_jis else 'ascii'
                    title = self.data[title_ptr:title_end].decode(encoding, errors='ignore')
                    logger.info(f"曲名: {title}")
                    
                    # タイトルをMIDIファイルのメタデータとして追加
                    self.midi.addTrackName(0, 0, title)
                else:
                    logger.warning("タイトルの取得に失敗しました")
                    title = "不明"
            except Exception as e:
                logger.warning(f"タイトルの取得中にエラーが発生しました: {e}")
                title = "不明"
            
            # トラック数と各トラックのオフセット取得（改良版）
            if len(self.data) <= 6:
                raise MDXFormatError("ファイルが短すぎます。トラック情報が含まれていません。")
                
            num_tracks = self.data[6]
            if num_tracks == 0 or num_tracks > 16 * 2:
                if self.force:
                    logger.warning(f"無効なトラック数({num_tracks})を{16}に制限します")
                    num_tracks = 16
                else:
                    raise MDXFormatError(f"無効なトラック数です: {num_tracks}")
                
            logger.info(f"トラック数: {num_tracks}")
            
            # トラックオフセットの取得と検証（改良版）
            track_offsets = []
            valid_track_count = 0
            for i in range(min(num_tracks, 16)):  # 最大トラック数を制限
                if 7 + i*2 + 1 >= len(self.data):
                    logger.warning(f"トラック{i+1}のオフセット情報が欠落しています")
                    break
                    
                offset = struct.unpack("<H", self.data[7 + i*2:9 + i*2])[0]
                
                if offset >= len(self.data):
                    logger.warning(f"トラック{i+1}のオフセット({offset})がファイルサイズを超えています")
                    if self.force:
                        continue  # このトラックをスキップ
                    else:
                        raise MDXFormatError(f"トラック{i+1}のオフセット({offset})がファイルサイズを超えています")
                
                track_offsets.append(offset)
                valid_track_count += 1
            
            # 強制モード時の特別処理
            if not track_offsets and self.force:
                logger.warning("有効なトラックが見つかりませんでした。強制モードで代替手段を試みます。")
                # 強制モードでは、ファイルの内容から有効なトラックデータを探す試み
                for i in range(0, min(len(self.data)-100, 0x1000), 0x100):
                    if i + 100 < len(self.data):
                        # 典型的なMDXコマンドパターンを探す
                        if any(cmd in self.data[i:i+100] for cmd in [MDX_CMD_TEMPO, MDX_CMD_VOLUME, MDX_CMD_INSTRUMENT]):
                            logger.info(f"オフセット0x{i:04X}で潜在的なトラックデータを検出しました")
                            track_offsets.append(i)
                            valid_track_count += 1
                            if valid_track_count >= 16:  # 最大トラック数
                                break
            
            # 少なくとも1つのトラックが必要
            if not track_offsets:
                if self.force:
                    logger.warning("トラックが見つからないため、デフォルトオフセットを使用します")
                    if len(self.data) > 100:
                        track_offsets.append(100)  # 適当なオフセット
                        valid_track_count = 1
                else:
                    raise MDXFormatError("有効なトラックが見つかりません")
            
            # 音色データの解析（可能であれば）
            self.parse_voice_data(voice_ptr)
            
            # 共通のテンポ設定
            self.midi.addTempo(0, 0, self.tempo)
            
            # 各トラックを解析
            for track_num, offset in enumerate(track_offsets):
                if track_num >= 16:  # MIDIは最大16チャンネル
                    logger.warning(f"トラック数が16を超えています。トラック{track_num+1}以降は無視されます。")
                    break
                    
                # トラックパラメータの初期化
                self.track_params[track_num] = {
                    'gate_time_ratio': 0.8,  # デフォルトゲートタイム比率
                    'detune': 0,            # デチューン値
                    'panpot': 64,           # パンポット（中央）
                    'volume': 100,          # ボリューム
                    'expression': 127,      # エクスプレッション
                    'instrument': track_num  # 楽器番号
                }
                
                logger.info(f"トラック {track_num+1} の解析中...")
                try:
                    self.parse_track(offset, track_num)
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
            
    def parse_voice_data(self, voice_ptr):
        """
        音色データを解析してGM音色へのマッピング情報を作成
        
        Args:
            voice_ptr (int): 音色データの開始位置
        """
        # 音色データが存在するか確認
        if voice_ptr == 0 or voice_ptr >= len(self.data):
            logger.warning("有効な音色データが見つかりません")
            return
            
        try:
            # 音色数を取得
            if voice_ptr + 1 >= len(self.data):
                return
                
            voice_count = self.data[voice_ptr]
            logger.debug(f"音色数: {voice_count}")
            
            # OPM音色データの分析
            pos = voice_ptr + 1
            for i in range(voice_count):
                # 各音色のパラメータを分析し、GM音色に変換するロジックを実装
                # これは実装が複雑になるため、単純化された実装を提供
                
                # バッファ境界チェック
                if pos + 4 >= len(self.data):
                    break
                    
                # OPM音色のタイプを解析（アルゴリズム、フィードバック等）
                # MDXの実装では、音色データは複雑な構造を持つ
                
                # 簡易的なマッピング（実際には音色分析に基づくべき）
                instrument_type = min(i, 127)  # 0-127の範囲に制限
                
                # 音色特性に基づく基本的なGM音色マッピング
                # 例：アルゴリズム0-3はピアノ系、4-5はギター系など
                
                # 実装簡略化のため、ここでは単純なマッピングを行う
                # 実際のOPM音色パラメータ解析は複雑で、完全な実装は難しい
                self.voice_mapping[i] = self.determine_gm_instrument(i)
                
                # 次の音色へ
                # 音色データの長さはフォーマットにより異なる場合がある
                # ここでは簡略化のため、固定長と仮定
                pos += 32  # 一般的なOPM音色データの長さ
                
        except Exception as e:
            logger.warning(f"音色データの解析中にエラーが発生しました: {e}")
            
    def determine_gm_instrument(self, opm_voice_num):
        """
        OPM音色番号からGM音色番号を推定
        
        Args:
            opm_voice_num (int): OPM音色番号
            
        Returns:
            int: GM音色番号(0-127)
        """
        # OPM音色番号からGM音色へのマッピング（基本版）
        # 実際には音色パラメータに基づく詳細な分析が必要
        
        # 基本的なカテゴリマッピング（音色番号の範囲に基づく）
        if opm_voice_num < 8:
            # 0-7: ピアノ系（0-7）
            return opm_voice_num
        elif opm_voice_num < 16:
            # 8-15: クロマチックパーカッション（8-15）
            return 8 + (opm_voice_num - 8)
        elif opm_voice_num < 24:
            # 16-23: オルガン系（16-23）
            return 16 + (opm_voice_num - 16)
        elif opm_voice_num < 32:
            # 24-31: ギター系（24-31）
            return 24 + (opm_voice_num - 24)
        elif opm_voice_num < 40:
            # 32-39: ベース系（32-39）
            return 32 + (opm_voice_num - 32)
        elif opm_voice_num < 48:
            # 40-47: ストリングス系（40-47）
            return 40 + (opm_voice_num - 40)
        elif opm_voice_num < 56:
            # 48-55: アンサンブル系（48-55）
            return 48 + (opm_voice_num - 48)
        elif opm_voice_num < 64:
            # 56-63: ブラス系（56-63）
            return 56 + (opm_voice_num - 56)
        elif opm_voice_num < 72:
            # 64-71: リード系（64-71）
            return 64 + (opm_voice_num - 64)
        elif opm_voice_num < 80:
            # 72-79: パイプ系（72-79）
            return 72 + (opm_voice_num - 72)
        elif opm_voice_num < 88:
            # 80-87: シンセリード系（80-87）
            return 80 + (opm_voice_num - 80)
        elif opm_voice_num < 96:
            # 88-95: シンセパッド系（88-95）
            return 88 + (opm_voice_num - 88)
        elif opm_voice_num < 104:
            # 96-103: シンセFX系（96-103）
            return 96 + (opm_voice_num - 96)
        elif opm_voice_num < 112:
            # 104-111: エスニック系（104-111）
            return 104 + (opm_voice_num - 104)
        elif opm_voice_num < 120:
            # 112-119: パーカッシブ系（112-119）
            return 112 + (opm_voice_num - 112)
        else:
            # 120-127: サウンドエフェクト系（120-127）
            return 120 + (opm_voice_num - 120) % 8

    def parse_track(self, offset, track_num):
        """
        トラックデータを解析してMIDIイベントに変換（改良版）
        
        Args:
            offset (int): トラックデータの開始オフセット
            track_num (int): トラック番号
            
        Raises:
            MDXFormatError: トラックデータの解析に失敗した場合
        """
        # トラック情報の初期化
        self.midi.addTrackName(track_num, 0, f"Track {track_num+1}")
        
        channel = track_num % 16
        self.channels.append(channel)
        
        # デフォルト楽器を設定
        params = self.track_params[track_num]
        instrument = params['instrument']
        self.midi.addProgramChange(track_num, channel, 0, instrument)
        
        # パンポットの初期設定
        self.midi.addControllerEvent(track_num, channel, 0, MIDI_CTRL_PAN, params['panpot'])
        
        # ボリュームの初期設定
        self.midi.addControllerEvent(track_num, channel, 0, MIDI_CTRL_VOLUME, params['volume'])
        
        # エクスプレッションの初期設定
        self.midi.addControllerEvent(track_num, channel, 0, MIDI_CTRL_EXPRESSION, params['expression'])
        
        # ピッチベンドレンジの設定（デチューン用）
        self.set_rpn(track_num, channel, 0, RPN_PITCH_BEND_RANGE, (24, 0))  # ±2オクターブ
        
        pos = offset
        self.time = 0
        loop_points = []  # (位置, 時間, 残りループ回数) のタプルのリスト
        
        try:
            while pos < len(self.data):
                cmd = self.data[pos]
                pos += 1
                
                if cmd >= MDX_CMD_NOTE and cmd <= 0xDF:  # ノートオン
                    note = cmd - MDX_CMD_NOTE
                    
                    # 境界チェック
                    if pos + 1 >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のノートデータが不完全です")
                        
                    # 次の2バイトは長さとボリューム
                    length = self.data[pos]
                    pos += 1
                    velocity = min(self.data[pos], 127)  # MIDIは最大127
                    pos += 1
                    
                    # デチューンの適用
                    if params['detune'] != 0:
                        # ピッチベンドで中間音を表現（改良版）
                        detune_value = self.calculate_pitch_bend(params['detune'])
                        self.midi.addPitchWheelEvent(track_num, channel, self.time, detune_value)
                    
                    # ゲートタイム比率を適用して音符の長さを決定
                    note_duration = length / 48 * params['gate_time_ratio']
                    
                    # ノートイベントの追加
                    self.midi.addNote(track_num, channel, note, self.time, note_duration, velocity)
                    
                    # タイムポインタの更新
                    self.time += length / 48
                    
                elif cmd == MDX_CMD_REST:  # 休符
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}の休符データが不完全です")
                        
                    length = self.data[pos]
                    pos += 1
                    self.time += length / 48
                    
                elif cmd == MDX_CMD_TEMPO:  # テンポ設定（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のテンポデータが不完全です")
                        
                    tempo_val = self.data[pos]
                    pos += 1
                    
                    if tempo_val == 0:
                        logger.warning(f"無効なテンポ値(0)を検出しました。デフォルト値を使用します。")
                        tempo_val = 200  # 適当なデフォルト値
                        
                    # MDXテンポ値からMIDIテンポ値（マイクロ秒/四分音符）を計算
                    self.tempo = self.calculate_midi_tempo(tempo_val)
                    logger.debug(f"テンポ変更: {60000000/self.tempo} BPM (MDX値: {tempo_val})")
                    self.midi.addTempo(track_num, self.time, int(60000000/self.tempo))
                    
                elif cmd == MDX_CMD_VOLUME:  # 音量設定（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}の音量データが不完全です")
                        
                    volume = min(self.data[pos], 127)
                    pos += 1
                    params['volume'] = volume
                    logger.debug(f"音量変更: {volume}")
                    self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_VOLUME, volume)
                    
                elif cmd == MDX_CMD_INSTRUMENT:  # 音色設定（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}の音色データが不完全です")
                        
                    opm_voice = self.data[pos]
                    pos += 1
                    
                    # OPM音色をGM音色にマッピング
                    instrument = self.opm_to_gm_instrument(opm_voice)
                    params['instrument'] = instrument
                    
                    logger.debug(f"音色変更: OPM音色={opm_voice} → GM音色={instrument}")
                    self.midi.addProgramChange(track_num, channel, self.time, instrument)
                    
                elif cmd == MDX_CMD_LOOPSTART:  # ループ開始（改良版）
                    logger.debug(f"ループ開始位置: {pos}, 時間: {self.time}")
                    loop_points.append((pos, self.time, 0))  # 回数は後で設定
                    
                elif cmd == MDX_CMD_LOOPEND:  # ループ終了（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のループ終了データが不完全です")
                        
                    if not loop_points:
                        logger.warning("ループ開始なしでループ終了が検出されました。無視します。")
                        pos += 1
                        continue
                        
                    loop_count = self.data[pos]
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
                
                elif cmd == MDX_CMD_DETUNE:  # デチューン（改良版）
                    if pos + 1 >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のデチューンデータが不完全です")
                        
                    detune_low = self.data[pos]
                    pos += 1
                    detune_high = self.data[pos]
                    pos += 1
                    
                    # 16ビット符号付き整数として解釈
                    detune = (detune_high << 8 | detune_low)
                    if detune & 0x8000:  # 負の値の場合
                        detune = detune - 0x10000
                    
                    params['detune'] = detune
                    
                    # ピッチベンドでデチューンを表現
                    detune_value = self.calculate_pitch_bend(detune)
                    self.midi.addPitchWheelEvent(track_num, channel, self.time, detune_value)
                    
                    logger.debug(f"デチューン設定: {detune} → ピッチベンド値: {detune_value}")
                
                elif cmd == MDX_CMD_GATE_TIME:  # ゲートタイム（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のゲートタイムデータが不完全です")
                        
                    gate_time = self.data[pos]
                    pos += 1
                    
                    # ゲートタイム比率を0.1～1.0の範囲で設定
                    # より正確な変換（MDXの仕様に基づく）
                    if gate_time <= 8:
                        # 8以下の場合は特殊処理
                        gate_time_ratio = max(0.1, gate_time / 8.0)
                    else:
                        # 基本的には百分率的な扱い
                        gate_time_ratio = min(1.0, gate_time / 100.0)
                        
                    params['gate_time_ratio'] = gate_time_ratio
                    logger.debug(f"ゲートタイム設定: {gate_time} → 比率: {gate_time_ratio}")
                
                elif cmd == MDX_CMD_PANPOT:  # パンポット（改良版）
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のパンポットデータが不完全です")
                        
                    pan_value = self.data[pos]
                    pos += 1
                    
                    # MDXのパンポット値をMIDIのパン値(0-127)に変換（より正確な実装）
                    # MDXの一般的な値: 0=左, 1=中央, 2=右, 3=中央
                    midi_pan = 64  # デフォルト中央
                    
                    if pan_value == 0:
                        midi_pan = 0    # 左
                    elif pan_value == 1:
                        midi_pan = 64   # 中央
                    elif pan_value == 2:
                        midi_pan = 127  # 右
                    elif pan_value == 3:
                        midi_pan = 64   # 中央（別表現）
                    
                    params['panpot'] = midi_pan
                    self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_PAN, midi_pan)
                    logger.debug(f"パンポット設定: MDX値={pan_value} → MIDI値={midi_pan}")
                
                elif cmd == MDX_CMD_PORTAMENTO:  # ポルタメント（改良版）
                    if pos + 1 >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のポルタメントデータが不完全です")
                    
                    # ポルタメントパラメータ（2バイト、符号付き整数）
                    porta_low = self.data[pos]
                    pos += 1
                    porta_high = self.data[pos]
                    pos += 1
                    
                    # 16ビット符号付き整数として解釈
                    porta_value = (porta_high << 8 | porta_low)
                    if porta_value & 0x8000:  # 負の値の場合
                        porta_value = porta_value - 0x10000
                    
                    # MIDIでのポルタメント表現（CC5:ポルタメント時間、CC65:ポルタメントオン/オフ）
                    # ポルタメントの効果を近似表現
                    porta_time = min(127, abs(porta_value) // 128)
                    
                    # ポルタメント有効化
                    if porta_value != 0:
                        self.midi.addControllerEvent(track_num, channel, self.time, 65, 127)  # ポルタメントオン
                        self.midi.addControllerEvent(track_num, channel, self.time, 5, porta_time)  # ポルタメント時間
                        logger.debug(f"ポルタメント設定: 値={porta_value}, 時間={porta_time}")
                    else:
                        self.midi.addControllerEvent(track_num, channel, self.time, 65, 0)  # ポルタメントオフ
                        logger.debug("ポルタメント無効化")
                
                elif cmd == MDX_CMD_LFO:  # LFO設定（改良版）
                    # LFO設定の詳細解析
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のLFOデータが不完全です")
                    
                    lfo_params = self.data[pos]
                    pos += 1
                    
                    # LFOタイプによってパラメータ数が異なる
                    param_count = 0
                    lfo_settings = {}
                    
                    # ビブラート（ピッチLFO）
                    if lfo_params & 0x01:
                        if pos + 1 >= len(self.data):
                            raise MDXFormatError(f"トラック{track_num+1}のLFOビブラートデータが不完全です")
                            
                        wave_period = self.data[pos]
                        pos += 1
                        wave_depth = self.data[pos]
                        pos += 1
                        param_count += 2
                        
                        lfo_settings['vibrato'] = {
                            'period': wave_period,
                            'depth': wave_depth
                        }
                        
                        # MIDIでのビブラート表現（モジュレーションホイール）
                        mod_depth = min(127, wave_depth)
                        self.midi.addControllerEvent(track_num, channel, self.time, 1, mod_depth)
                        logger.debug(f"ビブラート設定: 周期={wave_period}, 深さ={wave_depth}")
                    
                    # トレモロ（ボリュームLFO）
                    if lfo_params & 0x02:
                        if pos + 1 >= len(self.data):
                            raise MDXFormatError(f"トラック{track_num+1}のLFOトレモロデータが不完全です")
                            
                        wave_period = self.data[pos]
                        pos += 1
                        wave_depth = self.data[pos]
                        pos += 1
                        param_count += 2
                        
                        lfo_settings['tremolo'] = {
                            'period': wave_period,
                            'depth': wave_depth
                        }
                        
                        # MIDIでのトレモロ表現（エクスプレッション変化）
                        # 正確な表現は難しいため、近似的に実装
                        expr_depth = max(1, 127 - min(127, wave_depth))
                        self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_EXPRESSION, expr_depth)
                        logger.debug(f"トレモロ設定: 周期={wave_period}, 深さ={wave_depth}")
                    
                    # ハードウェアLFO
                    if lfo_params & 0x04:
                        if pos + 2 >= len(self.data):
                            raise MDXFormatError(f"トラック{track_num+1}のLFOハードウェアデータが不完全です")
                            
                        # 3バイトのパラメータ
                        hw_param1 = self.data[pos]
                        pos += 1
                        hw_param2 = self.data[pos]
                        pos += 1
                        hw_param3 = self.data[pos]
                        pos += 1
                        param_count += 3
                        
                        lfo_settings['hardware'] = {
                            'param1': hw_param1,
                            'param2': hw_param2,
                            'param3': hw_param3
                        }
                        
                        # ハードウェアLFOはMIDIで直接表現できないため、
                        # 関連するエフェクトで近似
                        logger.debug(f"ハードウェアLFO設定: パラメータ={hw_param1},{hw_param2},{hw_param3}")
                
                elif cmd == MDX_CMD_LFOON_PITCH:  # ピッチLFO ON
                    # ピッチLFOの有効化
                    # MIDIではモジュレーションホイールの値で近似
                    current_mod = 64  # 中程度のモジュレーション
                    self.midi.addControllerEvent(track_num, channel, self.time, 1, current_mod)
                    logger.debug("ピッチLFO有効化")
                
                elif cmd == MDX_CMD_LFOON_VOLUME:  # ボリュームLFO ON
                    # ボリュームLFOの有効化
                    # エクスプレッションコントローラーでトレモロを近似
                    self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_EXPRESSION, 100)
                    logger.debug("ボリュームLFO有効化")
                
                elif cmd == MDX_CMD_LFOFF_PITCH:  # ピッチLFO OFF
                    # ピッチLFOの無効化
                    self.midi.addControllerEvent(track_num, channel, self.time, 1, 0)
                    logger.debug("ピッチLFO無効化")
                
                elif cmd == MDX_CMD_LFOFF_VOLUME:  # ボリュームLFO OFF
                    # ボリュームLFOの無効化
                    self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_EXPRESSION, 127)
                    logger.debug("ボリュームLFO無効化")
                
                elif cmd == MDX_CMD_LFODELAY:  # LFOディレイ設定
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のLFOディレイデータが不完全です")
                        
                    lfo_delay = self.data[pos]
                    pos += 1
                    
                    # LFOディレイはMIDIで直接表現できないため、
                    # 情報のみ記録（後続のLFO ONコマンドで使用）
                    logger.debug(f"LFOディレイ設定: {lfo_delay}")
                
                elif cmd == MDX_CMD_KEYON_DELAY:  # キーオンディレイ
                    if pos >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のキーオンディレイデータが不完全です")
                        
                    keyon_delay = self.data[pos]
                    pos += 1
                    
                    # キーオンディレイ値をMIDIで表現するのは難しい
                    # ここでは情報を記録するのみ
                    logger.debug(f"キーオンディレイ設定: {keyon_delay}")
                
                elif cmd == MDX_CMD_OPM_REG:  # OPMレジスタ直接設定（改良版）
                    if pos + 1 >= len(self.data):
                        raise MDXFormatError(f"トラック{track_num+1}のOPMレジスタデータが不完全です")
                        
                    reg = self.data[pos]
                    pos += 1
                    value = self.data[pos]
                    pos += 1
                    
                    logger.debug(f"OPMレジスタ設定: レジスタ={reg:02X}h, 値={value:02X}h")
                    
                    # OPMレジスタからMIDIコントロールへの変換（拡張版）
                    if reg == 0x20:  # RL/FB/CONNECT (パンや効果に関連)
                        # パンポット制御
                        rl_bits = (value >> 6) & 0x03
                        if rl_bits == 0x01:  # Rのみ
                            midi_pan = 96  # 右寄り
                        elif rl_bits == 0x02:  # Lのみ
                            midi_pan = 32  # 左寄り
                        elif rl_bits == 0x03:  # 両方
                            midi_pan = 64  # 中央
                        else:  # 両方なし（通常ありえない）
                            midi_pan = 64  # 中央
                            
                        self.midi.addControllerEvent(track_num, channel, self.time, MIDI_CTRL_PAN, midi_pan)
                        
                        # フィードバック値（音色の豊かさに影響）
                        fb_value = (value >> 3) & 0x07
                        if fb_value > 0:
                            # フィードバック値が高いほど、音が豊かになる
                            # MIDIではコーラスエフェクトで近似
                            chorus_depth = min(127, fb_value * 18)
                            self.midi.addControllerEvent(track_num, channel, self.time, 93, chorus_depth)
                            
                    elif reg == 0x28:  # KEY CODE / FRACTION
                        # OPMのキーコード/分数設定（微分音程）
                        # MIDIでは直接対応するものがないため、ピッチベンドで近似
                        fraction = value & 0x3F
                        if fraction != 0:
                            bend_value = 8192 + int(fraction * (8192 / 64))
                            self.midi.addPitchWheelEvent(track_num, channel, self.time, bend_value)
                            
                    elif 0x40 <= reg <= 0x5F:  # DT1/MUL (各オペレータの設定)
                        # 特定のオペレータパラメータ変更
                        # MIDIでは直接対応するものがないが、
                        # 音色の特性に影響するため、記録しておく
                        op_num = (reg - 0x40) // 8
                        logger.debug(f"オペレータ{op_num+1}のDT1/MUL設定: {value:02X}h")
                        
                    elif 0x60 <= reg <= 0x7F:  # TL (各オペレータの音量)
                        # 特定のオペレータの音量設定
                        # MIDIではチャンネル全体のボリュームとして近似
                        if reg == 0x60:  # 最初のオペレータ（キャリア）
                            # TLは0が最大、127が最小なので反転
                            vol_value = 127 - min(127, value)
                            self.midi.addControllerEvent(track_num, channel, self.time, 
                                                         MIDI_CTRL_VOLUME, vol_value)
                            
                    elif 0xA0 <= reg <= 0xBF:  # AR/D1R (アタック/ディケイ)
                        # エンベロープのアタック/ディケイ設定
                        # MIDIではチャンネルアフタータッチで近似
                        attack = (value >> 4) & 0x0F
                        decay = value & 0x0F
                        if attack > 0:
                            # アタックが速いほど、チャンネルプレッシャーを強く
                            pressure = min(127, attack * 8)
                            self.midi.addChannelPressure(track_num, channel, self.time, pressure)
                
                else:  # その他の未対応コマンド（改良版）
                    # 未知のコマンドやバリエーションへの対応を強化
                    skip_bytes = 0
                    
                    # 既知の未対応コマンド
                    if 0x01 <= cmd <= 0x7F:  # 拡張コマンドやサブコマンド
                        # 多くの拡張コマンドは1バイトのパラメータを持つと仮定
                        skip_bytes = 1
                        if self.verbose:
                            logger.debug(f"拡張コマンド: 0x{cmd:02X} (パラメータ1バイトをスキップ)")
                    elif cmd == 0xF0 or cmd == 0xF5 or cmd == 0xF6 or cmd == 0xF7:
                        # 一部の特殊コマンド（実装による）
                        skip_bytes = 1
                        if self.verbose:
                            logger.debug(f"特殊コマンド: 0x{cmd:02X} (パラメータ1バイトをスキップ)")
                    elif cmd == 0xF1 or cmd == 0xF3:
                        # 2バイトパラメータを持つ特殊コマンド
                        skip_bytes = 2
                        if self.verbose:
                            logger.debug(f"特殊コマンド: 0x{cmd:02X} (パラメータ2バイトをスキップ)")
                    elif cmd == 0xFF:
                        # 終端コマンド（一部の実装で使用）
                        logger.debug("終端コマンド(0xFF)を検出。トラック解析を終了します。")
                        break
                    else:
                        # 完全に未知のコマンド - 安全のため1バイトのみスキップし警告
                        skip_bytes = 1
                        logger.warning(f"未知のコマンド: 0x{cmd:02X} at pos {pos-1}")
                    
                    # バッファ境界チェック
                    if pos + skip_bytes > len(self.data):
                        logger.warning(f"コマンド0x{cmd:02X}のデータが不完全です。処理を終了します。")
                        break
                        
                    pos += skip_bytes
        
        except Exception as e:
            logger.error(f"トラック{track_num+1}の解析中にエラーが発生しました: {e}")
            if not self.force:
                raise
    
    def calculate_pitch_bend(self, detune):
        """
        デチューン値からピッチベンド値を計算
        
        Args:
            detune (int): MDXのデチューン値
            
        Returns:
            int: MIDIピッチベンド値(0-16383、8192が中央)
        """
        # ピッチベンドの範囲: 0-16383 (8192が中央=ピッチ変更なし)
        # デチューン値を適切にスケーリング
        # 範囲は±2オクターブ（24半音）を想定
        
        # MDXデチューン値の範囲は実装により異なるが、
        # 一般的には±16384程度の範囲
        detune_range = 16384
        pitch_range = 8192  # 中央からの変位量
        
        # デチューン値をピッチベンド値に変換
        bend = 8192 + int((detune * pitch_range) / detune_range)
        
        # 範囲を0-16383に制限
        return max(0, min(16383, bend))
    
    def set_rpn(self, track, channel, time, rpn, value):
        """
        MIDIのRPN（登録済みパラメータ）を設定
        
        Args:
            track (int): トラック番号
            channel (int): チャンネル番号
            time (float): タイムポイント
            rpn (tuple): (MSB, LSB)のタプル
            value (tuple): (MSB, LSB)のデータ値
        """
        # RPN MSB/LSB
        self.midi.addControllerEvent(track, channel, time, MIDI_CTRL_RPN_MSB, rpn[0])
        self.midi.addControllerEvent(track, channel, time, MIDI_CTRL_RPN_LSB, rpn[1])
        
        # データエントリ MSB/LSB
        self.midi.addControllerEvent(track, channel, time, MIDI_CTRL_DATA_ENTRY_MSB, value[0])
        if len(value) > 1:
            self.midi.addControllerEvent(track, channel, time, MIDI_CTRL_DATA_ENTRY_LSB, value[1])
    
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
    parser = argparse.ArgumentParser(description="X68000 MDX to MIDI Converter - Improved Version")
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