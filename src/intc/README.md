# X-COM: Interceptor 日本語化パッチ（プログラム）

winmm.dll の代理 DLL です。文章のファイルを日本語版に差し替え、文字の描画を日本語に対応させます。

## 組み立て方
1. `python tools/make_patch.py` で build/patch.bin を作る
2. `src\build.bat` で build/winmm.dll を作り、ゲームのフォルダに置く

## 用意するもの
- Windows、Visual Studio 2022（cl・rc）、Python 3
- 原作のゲーム（Steam 版）。原作のファイルはここには入っていないので、各自用意してください。
- 訳のデータとフォントの元データもここには入っていません。

## ライセンス
MIT（リポジトリ直下の LICENSE）。
