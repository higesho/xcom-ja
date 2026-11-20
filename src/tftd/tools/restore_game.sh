#!/bin/sh
# テストで書き換わったゲームのフォルダを元に戻す（MISSDAT を元に、GAME_n は DUM.BIN だけに）
cd "$(dirname "$0")/../../TFD" || exit 1
cp -p ../_jp/orig/MISSDAT/* MISSDAT/
for d in GAME_1 GAME_2 GAME_3 GAME_4 GAME_5 GAME_6 GAME_7 GAME_8 GAME_9 GAME_10; do
  find "$d" -type f ! -name DUM.BIN -delete
done
ls MISSDAT | wc -l
