Pyqt music player


TODO:
implement icons


For user:
builds => releases



For develepor:
Python 3.11.8

python3.11 -m venv .env &&
source .env/bin/activate &&
pip install -r requirements.txt
python main.py


Linux build:
cd pulsepy/

mkdir build &&
wget https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O ./build/appimagetool-x86_64.AppImage && chmod +x ./build/appimagetool-x86_64.AppImage


./build/linuxdeploy-x86_64.AppImage \
  --appdir . \
  --desktop-file ./pulsepy.desktop \
  --icon-file ./icon.png \
  --output appimage &&
mv PulsePy_Music_Player-x86_64.AppImage ./build/release/PulsePy-x86_64.AppImage


Copyright:
Icon: <a href="https://www.flaticon.com/free-icons/music" title="music icons">Music icons created by Freepik - Flaticon</a>