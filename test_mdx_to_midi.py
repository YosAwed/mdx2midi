#!/usr/bin/env python3
"""
MDX to MIDI コンバーターのテストスクリプト
"""

import os
import unittest
import tempfile
from mdx_to_midi import MDXtoMIDI, MDXFormatError

class TestMDXtoMIDI(unittest.TestCase):
    """
    MDXtoMIDI クラスのテストケース
    """
    
    def setUp(self):
        """
        テスト環境のセットアップ
        """
        # テスト用の一時ディレクトリを作成
        self.test_dir = tempfile.TemporaryDirectory()
        self.output_midi = os.path.join(self.test_dir.name, "output.mid")
    
    def tearDown(self):
        """
        テスト環境のクリーンアップ
        """
        self.test_dir.cleanup()
    
    def test_validate_mdx_file_not_found(self):
        """
        存在しないファイルの検証テスト
        """
        converter = MDXtoMIDI("not_exists.mdx", self.output_midi)
        with self.assertRaises(FileNotFoundError):
            converter.validate_mdx_file()
    
    def test_validate_mdx_file_too_small(self):
        """
        サイズが小さすぎるファイルの検証テスト
        """
        # 小さすぎるMDXファイルを作成
        test_mdx = os.path.join(self.test_dir.name, "small.mdx")
        with open(test_mdx, "wb") as f:
            f.write(b"\x00\x00\x00")  # 3バイトだけのファイル
        
        converter = MDXtoMIDI(test_mdx, self.output_midi)
        with self.assertRaises(MDXFormatError):
            converter.validate_mdx_file()
    
    def test_validate_mdx_file_invalid_pointers(self):
        """
        無効なポインタを持つファイルの検証テスト
        """
        # 無効なポインタを持つMDXファイルを作成
        test_mdx = os.path.join(self.test_dir.name, "invalid_pointers.mdx")
        with open(test_mdx, "wb") as f:
            # タイトルポインタと音色ポインタが小さすぎる値
            f.write(b"\x02\x00\x03\x00\x00\x00\x01")
        
        converter = MDXtoMIDI(test_mdx, self.output_midi)
        with self.assertRaises(MDXFormatError):
            converter.validate_mdx_file()
    
    def test_parse_track_boundary_check(self):
        """
        トラック解析時の境界チェックテスト
        """
        # 不完全なトラックデータを持つMDXファイルを作成
        test_mdx = os.path.join(self.test_dir.name, "incomplete_track.mdx")
        with open(test_mdx, "wb") as f:
            # ヘッダー: タイトルポインタ=10, 音色ポインタ=20, トラック数=1
            f.write(b"\x0A\x00\x14\x00\x00\x00\x01")
            # トラック1のオフセット=30
            f.write(b"\x1E\x00")
            # タイトル (位置10)
            f.write(b"\x00" * 3)
            f.write(b"Test\x00")
            # 音色データ (位置20)
            f.write(b"\x00" * 5)
            # トラックデータ (位置30) - 不完全なノートコマンド
            f.write(b"\x80")
        
        converter = MDXtoMIDI(test_mdx, self.output_midi)
        # read_mdxを呼び出すと、トラック解析中にMDXFormatErrorが発生するはず
        with self.assertRaises(MDXFormatError):
            converter.read_mdx()
    
    def test_loop_handling(self):
        """
        ループ処理のテスト
        """
        # ループを含むMDXファイルを作成
        test_mdx = os.path.join(self.test_dir.name, "loop_test.mdx")
        with open(test_mdx, "wb") as f:
            # ヘッダー: タイトルポインタ=10, 音色ポインタ=20, トラック数=1
            f.write(b"\x0A\x00\x14\x00\x00\x00\x01")
            # トラック1のオフセット=30
            f.write(b"\x1E\x00")
            # タイトル (位置10)
            f.write(b"\x00" * 3)
            f.write(b"Loop Test\x00")
            # 音色データ (位置20)
            f.write(b"\x00" * 5)
            # トラックデータ (位置30)
            # ループ開始
            f.write(b"\xE1")
            # ノート
            f.write(b"\x80\x10\x7F")
            # ループ終了 (2回)
            f.write(b"\xE2\x02")
            # 終了
            f.write(b"\x00\x10")
        
        # ループ回数を2に制限
        converter = MDXtoMIDI(test_mdx, self.output_midi, max_loops=2)
        converter.read_mdx()
        converter.save_midi()
        
        # MIDIファイルが生成されたことを確認
        self.assertTrue(os.path.exists(self.output_midi))
        self.assertGreater(os.path.getsize(self.output_midi), 0)
    
    def test_max_loops_limit(self):
        """
        最大ループ回数制限のテスト
        """
        # ループを含むMDXファイルを作成 (多数のループ)
        test_mdx = os.path.join(self.test_dir.name, "many_loops.mdx")
        with open(test_mdx, "wb") as f:
            # ヘッダー: タイトルポインタ=10, 音色ポインタ=20, トラック数=1
            f.write(b"\x0A\x00\x14\x00\x00\x00\x01")
            # トラック1のオフセット=30
            f.write(b"\x1E\x00")
            # タイトル (位置10)
            f.write(b"\x00" * 3)
            f.write(b"Many Loops\x00")
            # 音色データ (位置20)
            f.write(b"\x00" * 5)
            # トラックデータ (位置30)
            # ループ開始
            f.write(b"\xE1")
            # ノート
            f.write(b"\x80\x10\x7F")
            # ループ終了 (10回 - 通常は多すぎる)
            f.write(b"\xE2\x0A")
            # 終了
            f.write(b"\x00\x10")
        
        # ループ回数を1に制限
        converter = MDXtoMIDI(test_mdx, self.output_midi, max_loops=1)
        converter.read_mdx()
        converter.save_midi()
        
        # MIDIファイルが生成されたことを確認
        self.assertTrue(os.path.exists(self.output_midi))

if __name__ == "__main__":
    unittest.main()
