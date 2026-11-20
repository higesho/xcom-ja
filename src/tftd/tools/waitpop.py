# 地球の画面で時間を進め、窓（探知・任務など）が出るまで待つ。python tools/waitpop.py [秒] [名前]
import sys, time, subprocess, os
from PIL import Image
R = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
lim = float(sys.argv[1]) if len(sys.argv) > 1 else 120
name = sys.argv[2] if len(sys.argv) > 2 else 'pop'
t = time.time()
while time.time() - t < lim:
    time.sleep(4)
    subprocess.run([sys.executable, os.path.join(R, 'tools', 'win.py'), 'shot', name], stdout=subprocess.DEVNULL)
    im = Image.open(os.path.join(R, 'capture', name + '.png')).convert('RGB')
    p = im.getpixel((100, 240))
    if p == (0, 56, 40) or im.getpixel((70, 200)) in ((132, 132, 176), (188, 188, 212)):
        print('popup', round(time.time() - t)); break
else:
    print('timeout')
