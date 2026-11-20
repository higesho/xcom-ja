# X-COM: Enforcer 日本語化パッチ（プログラム）

winmm.dll の代理 DLL です。.int ファイルを日本語版に差し替え、日本語の字のページをフォントに足します。

## 組み立て方
1. `python tools/extract.py` で英語の文を取り出す
2. `python tools/make_patch.py` で build/patch.bin を作る（日本語の字のパッケージはゲームの UCC で作るので、ゲームのコピーが要る）
3. `src\build.bat` で build/winmm.dll を作り、ゲームの System フォルダに置く

## 用意するもの
- Windows、Visual Studio 2022（cl・rc）、Python 3
- 原作のゲーム（Steam 版）。原作のファイルはここには入っていないので、各自用意してください。
- 訳のデータとフォントの元データもここには入っていません。

## ライセンス
MIT（リポジトリ直下の LICENSE）。
