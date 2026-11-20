# X-COM: Terror from the Deep 日本語化パッチ（プログラム）

DOSBox 用の winmm.dll です。起動時に文章のファイルと EXE を日本語版に差し替え、文字の描画を日本語に対応させます。

## 組み立て方
1. `python tools/extract.py` で英語の文を取り出す
2. `python tools/make_patch.py` で build/patch.bin を作る
3. `src\build.bat` で build/winmm.dll を作り、ゲームのフォルダに置く

## 用意するもの
- Windows、Visual Studio 2022（cl・rc）、Python 3
- 原作のゲーム（Steam 版）。原作のファイルはここには入っていないので、各自用意してください。
- 訳のデータとフォントの元データもここには入っていません。

## ライセンス
MIT（リポジトリ直下の LICENSE）。
