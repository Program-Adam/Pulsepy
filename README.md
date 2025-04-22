🎵 **PyQt Music Player - Simple and Sweet** 🎵

Enjoy your music with this straightforward, single-file PyQt5 player.

[preview.png]

**Features:**

* Clean and intuitive interface.
* [Future: Icons for a polished look!]

**Downloads:**

* Ready-to-use builds: [Link to your releases](https://github.com/Program-Adam/Pulsepy/releases/tag/v1.0.0)

**Under the Hood (for developers):**

Built with Python 3.11.8 and PyQt5.

**Quick Start (development):**

    python3.11 -m venv .env && \
    source .env/bin/activate && \
    pip install -r requirements.txt && \
    python main.py

**Linux AppImage Creation:**

    cd pulsepy/

    mkdir build && \
    wget https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O ./build/appimagetool-x86_64.AppImage && \
    chmod +x ./build/appimagetool-x86_64.AppImage

    ./build/linuxdeploy-x86_64.AppImage \
      --appdir . \
      --desktop-file ./pulsepy.desktop \
      --icon-file ./icon.png \
      --output appimage && \
    mv PulsePy_Music_Player-x86_64.AppImage ./build/release/PulsePy-x86_64.AppImage

**Credits:**

Icon: [Music icons created by Freepik - Flaticon](https://www.flaticon.com/free-icons/music)
