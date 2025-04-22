'''
Completly different Music Player with a simplistic Design
'''

import os
import sys
import re
import time
import random
from collections import deque

import numpy as np
import sounddevice as sd
import soundfile as sf
from pydub import AudioSegment

from PyQt5.QtCore import (
    Qt, QEvent, QObject, QPropertyAnimation, QRect, QTimer, QThread, pyqtSignal, QTime
)
from PyQt5.QtGui import QColor, QPainter, QBrush, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QTimeEdit, QLineEdit, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QStyleOptionSlider, QStyle, QMenu, QAction
)


class PlaylistControl:
    REPEAT_NONE = 0
    REPEAT_ALL = 1
    REPEAT_ONE = 2

    def __init__(self, song_list=None):
        self.song_list = song_list or []
        self.current_index = 0
        self.shuffle_mode = False
        self.repeat_mode = PlaylistControl.REPEAT_NONE
        self._shuffle_order = []
        self._shuffle_pos = 0

    def set_playlist(self, song_list):
        self.song_list = song_list
        self.current_index = 0
        self._reset_shuffle()

    def set_shuffle(self, enabled):
        self.shuffle_mode = enabled
        self._reset_shuffle()

    def current_song(self):
        if not self.song_list:
            return None
        if self.shuffle_mode:
            return self.song_list[self._shuffle_order[self._shuffle_pos]]
        return self.song_list[self.current_index]

    def next_song(self):
        if not self.song_list:
            return None

        if self.repeat_mode == PlaylistControl.REPEAT_ONE:
            # Stay on current song
            return self.current_song()

        if self.shuffle_mode:
            self._shuffle_pos += 1
            if self._shuffle_pos >= len(self.song_list):
                if self.repeat_mode == PlaylistControl.REPEAT_ALL:
                    self._reset_shuffle()
                else:
                    self._shuffle_pos = len(self.song_list) - 1  # Stay at last song
            return self.current_song()
        else:
            self.current_index += 1
            if self.current_index >= len(self.song_list):
                if self.repeat_mode == PlaylistControl.REPEAT_ALL:
                    self.current_index = 0
                else:
                    self.current_index = len(self.song_list) - 1  # Stay at last song
            return self.current_song()

    def previous_song(self):
        if not self.song_list:
            return None

        if self.repeat_mode == PlaylistControl.REPEAT_ONE:
            # Stay on current song
            return self.current_song()

        if self.shuffle_mode:
            self._shuffle_pos -= 1
            if self._shuffle_pos < 0:
                if self.repeat_mode == PlaylistControl.REPEAT_ALL:
                    self._shuffle_pos = len(self.song_list) - 1
                else:
                    self._shuffle_pos = 0
            return self.current_song()
        else:
            self.current_index -= 1
            if self.current_index < 0:
                if self.repeat_mode == PlaylistControl.REPEAT_ALL:
                    self.current_index = len(self.song_list) - 1
                else:
                    self.current_index = 0
            return self.current_song()

    def _reset_shuffle(self):
        if self.shuffle_mode and self.song_list:
            self._shuffle_order = list(range(len(self.song_list)))
            random.shuffle(self._shuffle_order)
            self._shuffle_pos = 0
        else:
            self._shuffle_order = []
            self._shuffle_pos = 0

    def go_to_song(self, index):
        if not self.song_list or not (0 <= index < len(self.song_list)):
            return
        if self.shuffle_mode:
            if index in self._shuffle_order:
                self._shuffle_pos = self._shuffle_order.index(index)
        else:
            self.current_index = index 


    def get_playlist(self):
        # Returns a Python list of all item texts in the QListWidget
        return [self.song_list.item(i).text() for i in range(self.song_list.count())]



class AudioPlayer(QThread):
    chunk_signal = pyqtSignal(np.ndarray)
    position_signal = pyqtSignal(int)
    song_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.file = None
        self.fs = None
        self.stop_flag = False
        self.pause_flag = False
        self.position = 0  # in frames
        self.blocksize = 1024
        self.stream = None
        self.volume = 1.0
        self.filename = None
        self.channels = 2
        self.file_obj = None  # soundfile.SoundFile object
        self.seek_flag = False
        self.seek_target = 0
        self.seconds_elapsed = 0
        self.seconds_total = 1


    def load(self, filename):
        try:
            if self.isRunning():
                self.stop()
                self.wait()
            self.filename = filename
            self.file_obj = sf.SoundFile(filename, 'r')
            self.fs = self.file_obj.samplerate
            self.channels = self.file_obj.channels
            self.position = 0
            self.total_frames = len(self.file_obj) 
        except:
            print("ERROR: File" + filename + "not found.")



    def run(self):
        self.stop_flag = False
        self.pause_flag = False

        with sf.SoundFile(self.filename, 'r') as f:
            self.total_frames = len(f)
            self.fs = f.samplerate
            self.seconds_total = int(self.total_frames /self.fs)
            self.channels = f.channels
            self.stream = sd.OutputStream(
                samplerate=self.fs, channels=self.channels, dtype="float32", blocksize=self.blocksize
            )
            self.stream.start()
            f.seek(self.position)
            try:
                while not self.stop_flag:
                    # ---- Handle seek even when paused ----
                    if self.pause_flag:
                        if self.seek_flag:
                            f.seek(self.seek_target)
                            self.position = self.seek_target
                            self.seek_flag = False
                            self.position_signal.emit(self.position)
                        self.msleep(100)
                        continue

                    # ---- Handle seek during playback ----
                    if self.seek_flag:
                        f.seek(self.seek_target)
                        self.position = self.seek_target
                        self.seek_flag = False
                        self.position_signal.emit(self.position)
                    data = f.read(self.blocksize, dtype='float32')
                    if len(data) == 0:
                        break
                    if data.ndim == 1:
                        data = np.expand_dims(data, axis=1)
                    data = data * self.volume
                    self.stream.write(data)
                    self.chunk_signal.emit(data.copy())
                    self.position = f.tell()
                    self.seconds_elapsed = self.position / self.fs
                    self.position_signal.emit(self.position)

            finally:
                if self.stream:
                    self.stream.stop()
                    self.stream.close()
                    self.stream = None
                self.song_finished.emit()



    def stop(self):
        self.stop_flag = True
        self.pause_flag = False  # Also clear pause state
        # Do NOT close or abort the stream here!
        # Let the thread's run() handle it.


    def pause(self):
        self.pause_flag = True

    def resume(self):
        self.pause_flag = False

    def set_volume(self, value):
        self.volume = value / 100.0

    def seek(self, frame):
        """Request a seek to a specific frame in the file."""
        self.seek_target = frame
        self.seek_flag = True



import numpy as np
import random
from collections import deque
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import QTimer, QRect, Qt
from PyQt5.QtGui import QPainter, QColor, QBrush

class Visualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #23272f; border-radius: 18px;")
        self.num_bars = 30
        self.amplitude = [0] * self.num_bars
        self.target_amplitude = [0] * self.num_bars
        self.amp_history = [deque([0]*3, maxlen=3) for _ in range(self.num_bars)]
        self.hue = 0

        self.setFixedHeight(100)
        self.max_height = self.height()
        x = np.linspace(0, np.pi, self.num_bars)
        self.cos_curve = 0.7 * (np.cos(x - np.pi/2) * 0.5 + 0.5) + 0.3

        # Smoothing factors
        self.smooth_attack = 0.7
        self.smooth_release = 0.1
        self.max_delta = 2.0

        # fade out animation
        self._stopping = False
        self._fade_starts = None  # List of per-bar fade start times
        self._fade_elapsed = 0    # Time since fade started (in timer ticks)
        self._fade_delay = 3      # Delay (in timer ticks) between each bar's fade start
        self._fade_line = None  # y-coordinate of the fade line
        self._fade_speed = 10   # pixels per timer tick
        
        # Modern fade-out animation (per-bar alpha)
        self._fade_alpha = [255] * self.num_bars
        self._fade_active = False
        self._fade_tick = 0
        self._fade_duration = 15   # How many ticks each bar takes to fade
        self._fade_stagger = 2     # Ticks to wait between each bar's fade start
        self._fully_faded = False 

        # Dynamic boost
        self.boost_side = None
        self.boost_timer = 0
        self.boost_duration = 8
        self.boost_interval = 25
        self.boost_strength = 1.7

        # Latest chunk buffer
        self.latest_chunk = None

        # Timer drives both amplitude update and repaint
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer)
        self.timer.start(50)

    def update_visualization(self, chunk):
        """Store the latest chunk for processing in timer."""
        self.latest_chunk = chunk
    
    def pause(self):
        """Start modern, staggered fade-out animation."""
        self.latest_chunk = None
        self._stopping = True
        self._fade_active = True
        self._fade_tick = 0
        self._fade_alpha = [255] * self.num_bars
        self._fully_faded = False
        if not self.timer.isActive():
            self.timer.start(50)

    def resume(self):
        self._stopping = False
        self._fade_active = False
        self._fade_alpha = [255] * self.num_bars
        self._fully_faded = False
        self.timer.start(50)



    def on_timer(self):
        if self._fade_active:
            all_done = True
            for i in range(self.num_bars):
                bar_fade_start = i * self._fade_stagger
                if self._fade_tick >= bar_fade_start and self._fade_alpha[i] > 0:
                    progress = (self._fade_tick - bar_fade_start) / self._fade_duration
                    new_alpha = int(255 * (1 - min(max(progress, 0), 1)))
                    self._fade_alpha[i] = new_alpha
                if self._fade_alpha[i] > 0:
                    all_done = False
            self._fade_tick += 1
            self.update()
            if all_done:
                self.timer.stop()
                self._stopping = False
                self._fade_active = False
                self._fully_faded = True  # Bars are now gone
                self.update()  # Trigger a final repaint
        else:
            self.process_amplitude()
            self.update()

    def process_amplitude(self):
        """Update and smooth amplitude values."""
        chunk = self.latest_chunk
        if chunk is None or len(chunk) == 0:
            self.target_amplitude = [0] * self.num_bars
        else:
            if chunk.ndim > 1:
                data = chunk[:, 0]
            else:
                data = chunk
            data = data[:self.num_bars*int(len(data)/self.num_bars)]
            if len(data) == 0:
                self.target_amplitude = [0] * self.num_bars
            else:
                split = np.array_split(data, self.num_bars)
                self.target_amplitude = [
                    np.sqrt(np.mean(s**2)) for s in split
                ]

        # Dynamic boost logic
        if self.boost_timer > 0:
            mid = self.num_bars // 2
            if self.boost_side == 'left':
                for i in range(mid):
                    self.target_amplitude[i] *= self.boost_strength
            elif self.boost_side == 'right':
                for i in range(mid, self.num_bars):
                    self.target_amplitude[i] *= self.boost_strength
            self.boost_timer -= 1
        else:
            if random.randint(1, self.boost_interval) == 1:
                self.boost_side = random.choice(['left', 'right'])
                self.boost_timer = self.boost_duration
            else:
                self.boost_side = None

        for i in range(self.num_bars):
            self.amp_history[i].append(self.target_amplitude[i])
            avg = sum(self.amp_history[i]) / len(self.amp_history[i])
            if avg > self.amplitude[i]:
                factor = self.smooth_attack
            else:
                factor = self.smooth_release
            smoothed = factor * avg + (1 - factor) * self.amplitude[i]
            delta = smoothed - self.amplitude[i]
            if abs(delta) > self.max_delta:
                smoothed = self.amplitude[i] + np.sign(delta) * self.max_delta
            self.amplitude[i] = smoothed

    def resizeEvent(self, event):
        self.max_height = self.height()
        x = np.linspace(0, np.pi, self.num_bars)
        self.cos_curve = 0.7 * (np.cos(x - np.pi/2) * 0.5 + 0.5) + 0.3
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._fully_faded:
            # Fill with transparent or background color, no bars
            painter = QPainter(self)
            painter.fillRect(self.rect(), self.palette().window())
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bar_width = self.width() / self.num_bars
        self.hue = (self.hue + 3) % 360

        max_amp = max(max(self.amplitude), 1e-6)
        for i, amp in enumerate(self.amplitude):
            bar_hue = (self.hue + i * (360 // self.num_bars)) % 360
            alpha = self._fade_alpha[i] if self._fade_active else 180
            color = QColor.fromHsv(bar_hue, 255, 255, alpha)
            normalized_amp = amp / max_amp if max_amp > 0 else 0
            bar_max = self.cos_curve[i] * self.max_height
            bar_height = int(normalized_amp * bar_max)
            bar_top = self.height() - bar_height

            rect = QRect(
                int(i * bar_width), bar_top,
                int(bar_width * 0.8), bar_height
            )

            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 6, 6)


class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PulsePy Musicplayer")
        self.setGeometry(100, 100, 400, 700)
        self.setFixedWidth(600)

        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("""
            QMainWindow {
                background-color: #23272f;
                border-radius: 18px;
            }
            QPushButton {
                background-color: #426cf5;
                color: white;
                border-radius: 16px;
                padding: 10px 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #3356b8;
            }
            QSlider::groove:horizontal {
                border-radius: 8px;
                height: 8px;
                background: #333;
            }
            QSlider::handle:horizontal {
                background: #426cf5;
                border-radius: 8px;
                width: 18px;
                margin: -5px 0;
            }
        """)

        # --- Variables ---
        self._slider_seeking = False
        self._slider_value = 0

        self.audio_player = AudioPlayer()
        self.audio_player.position_signal.connect(self.update_slider_position)
        self.audio_player.song_finished.connect(self.song_finished)

        # stores all audio file in { "Edsheeran - XYZ", "/home/lunar/Music/Edsheeran - XYZ"}
        self.loaded_files = {}
        self.playlist = PlaylistControl()
        self.is_playing = False
        self.no_slider_update = False
        self.repeat_all = False
        self.timeedit_update = [True, True]
        self.tmp_qtime = QTime(0,0,0,0)
        self.current_folder = ""

        self.init_ui()
    
    # every 500ms
    def update(self):
        if len(self.song_list) > 1:
            self.search_bar.setPlaceholderText(f"Search songs ({len(self.song_list)})...")
        else:
            self.search_bar.setPlaceholderText(f"Search songs...")



    # --- Extra ---
    def format_time(self, seconds):
        seconds = int(seconds)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"

    def get_audio_files(self, folder):
        audio_extensions = ('.mp3', '.wav', '.flac', '.ogg', '.aiff')
        return [
            os.path.abspath(os.path.join(folder, f))
            for f in os.listdir(folder)
            if f.lower().endswith(audio_extensions)
        ]

    def filter_song_list(self, text):
        # Step 1: Remember the currently selected item (by reference or text)
        current_item = self.song_list.currentItem()
        current_text = current_item.text() if current_item else None

        # Step 2: Filter items (hide those that don't match)
        for i in range(self.song_list.count()):
            item = self.song_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

        # Step 3: After filtering, if the previously selected item is still visible, re-select it
        if current_text:
            for i in range(self.song_list.count()):
                item = self.song_list.item(i)
                if not item.isHidden() and item.text() == current_text:
                    self.song_list.setCurrentItem(item)
                    break
    
    # Helper to create QTime safely (max 23 hours)
    def safe_qtime(self, seconds):
        hours = min(seconds // 3600, 23)
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return QTime(hours, minutes, secs)                 



    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)

        # --- Visualizer ---
        self.visualizer = Visualizer(self)
        self.audio_player.chunk_signal.connect(self.visualizer.update_visualization)
        main_layout.addWidget(self.visualizer)

        self.song_label = CustomLabel("No song loaded")
        self.song_label.setAlignment(Qt.AlignCenter)
        self.song_label.setStyleSheet(Styles.label)
        main_layout.addWidget(self.song_label)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search songs...")
        self.search_bar.textChanged.connect(self.filter_song_list)
        self.search_bar.setStyleSheet(Styles.search_bar)
        main_layout.addWidget(self.search_bar)

        # --- Song List and Playlist Management Side by Side ---
        song_playlist_layout = QHBoxLayout()

        # Song List (left)
        self.song_list = QListWidget()
        self.song_list.setItemDelegate(ElideDelegate(self.song_list))
        self.song_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.song_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.song_list.setWordWrap(False)
        self.song_list.setMinimumHeight(120)
        self.song_list.setFixedWidth(400)
        self.song_list.itemClicked.connect(self.handle_song_selection)
        self.song_list.setStyleSheet(Styles.song_list)
        self.song_list.setDragDropMode(QListWidget.InternalMove)
        self.song_list.setDefaultDropAction(Qt.MoveAction)
        self.song_list.setSelectionMode(QListWidget.SingleSelection)
        self.song_list.model().rowsMoved.connect(self.on_song_list_reordered)
        self.song_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.song_list.customContextMenuRequested.connect(self.show_song_list_context_menu)

        song_playlist_layout.addWidget(self.song_list)

        # Playlist Management Panel (right)
        playlist_mgmt_layout = QVBoxLayout()
        playlist_mgmt_layout.setSpacing(8)

        self.save_playlist_btn = QPushButton("Save Playlist")
        self.save_playlist_btn.setCursor(Qt.PointingHandCursor)
        self.save_playlist_btn.clicked.connect(self.save_playlist)
        self.save_playlist_btn.setStyleSheet(Styles.btn_style)
        playlist_mgmt_layout.addWidget(self.save_playlist_btn)

        self.load_playlist_btn = QPushButton("Load Playlist")
        self.load_playlist_btn.setCursor(Qt.PointingHandCursor)
        self.load_playlist_btn.clicked.connect(self.load_playlist)
        self.load_playlist_btn.setStyleSheet(Styles.btn_style)
        playlist_mgmt_layout.addWidget(self.load_playlist_btn)
        
        # Create a horizontal layout for the navigation buttons
        nav_layout = QHBoxLayout()

        self.back_btn = QPushButton("◀")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.previous_song)
        self.back_btn.setStyleSheet(Styles.btn_style)
        self.back_btn.setToolTip("Last Song")
        nav_layout.addWidget(self.back_btn)

        self.skip_btn = QPushButton("▶")
        self.skip_btn.setCursor(Qt.PointingHandCursor)
        self.skip_btn.clicked.connect(self.play_next_song)
        self.skip_btn.setStyleSheet(Styles.btn_style)
        self.skip_btn.setToolTip("Next Song")
        nav_layout.addWidget(self.skip_btn)

        # Add the navigation layout to your playlist management layout
        playlist_mgmt_layout.addLayout(nav_layout)


        song_playlist_layout.addLayout(playlist_mgmt_layout)
        main_layout.addLayout(song_playlist_layout)

        # --- Progress/Seek Bar with Time ---
        progress_layout = QHBoxLayout()

        # Current time input
        self.current_time_edit = AdvancedTimeEdit(QTime(0, 0))
        self.current_time_edit.setDisplayFormat("mm:ss")
        self.current_time_edit.setAlignment(Qt.AlignCenter)
        self.current_time_edit.setButtonSymbols(QTimeEdit.NoButtons)  # Hide up/down arrows
        self.current_time_edit.setStyleSheet(Styles.timeedit)
        self.current_time_edit.setFixedWidth(80)
        self.current_time_edit.editStarted.connect(self.on_current_time_edit_started)
        self.current_time_edit.editingFinished.connect(self.current_time_edit_finished)
        self.current_time_edit.setEnabled(False)
        progress_layout.addWidget(self.current_time_edit)

        # Progress slider as before...
        self.progress_slider = ClickableSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setFixedHeight(30)
        self.progress_slider.sliderMoved.connect(self.slider_was_moved)
        self.progress_slider.sliderReleased.connect(self.slider_was_released)
        self.progress_slider.sliderClicked.connect(self.on_slider_clicked)
        self.progress_slider.setStyleSheet(Styles.progress_slider)
        progress_layout.addWidget(self.progress_slider, stretch=1)
        self.progress_slider.setValue(self.progress_slider.maximum())
        self.progress_slider.setEnabled(False)

        # Total time input
        self.total_time_edit = AdvancedTimeEdit(QTime(0, 0))
        self.total_time_edit.setDisplayFormat("mm:ss")
        self.total_time_edit.setAlignment(Qt.AlignCenter)
        self.total_time_edit.setButtonSymbols(QTimeEdit.NoButtons)
        self.total_time_edit.setStyleSheet(Styles.timeedit)
        self.total_time_edit.setFixedWidth(80)
        self.total_time_edit.editStarted.connect(self.on_total_time_edit_started)
        self.total_time_edit.editingFinished.connect(self.total_time_edit_edit_finished)
        self.total_time_edit.setEnabled(False)
        progress_layout.addWidget(self.total_time_edit)
        main_layout.addLayout(progress_layout)

        


        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.update)
        self.progress_timer.start(500)  # update twice a second

        # --- Controls Layout ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)

        self.folder_btn = QPushButton("Select Music")
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.clicked.connect(self.open_file_or_folder)
        self.folder_btn.setStyleSheet(Styles.btn_style)
        controls_layout.addWidget(self.folder_btn)

        self.play_pause_btn = QPushButton("Play")
        self.play_pause_btn.setCursor(Qt.PointingHandCursor)
        self.play_pause_btn.clicked.connect(self.play_pause)
        self.play_pause_btn.setStyleSheet(Styles.btn_style)
        controls_layout.addWidget(self.play_pause_btn)

        # --- Repeat/Shuffle Button (to the right of play button) ---
        self.playback_mode_btn = QPushButton("Repeat Off")
        self.playback_mode_btn.setCursor(Qt.PointingHandCursor)
        self.playback_mode_btn.clicked.connect(self.toggle_playback_mode)
        self.playback_mode_btn.setStyleSheet(Styles.btn_style)
        controls_layout.addWidget(self.playback_mode_btn)

        main_layout.addLayout(controls_layout)

        # --- Set main widget/layout ---
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # --- Playback mode state ---
        self.playback_modes = ['Repeat Off', 'Repeat One', 'Repeat All', 'Shuffle']
        self.current_playback_mode = 0

    # --- Slider ---
    def format_time(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours:02}:{minutes:02}:{secs:02}"
        else:
            return f"{minutes:02}:{secs:02}"



    def slider_was_moved(self, value):
        """Called when the user moves the slider handle."""
        self.no_slider_update = True

        target_frame = int((self.progress_slider.value() / 1000) * self.audio_player.total_frames)
        fs = self.audio_player.fs
        total_frames = self.audio_player.total_frames

        current_seconds = int(target_frame / fs)
        total_seconds = int(total_frames / fs)
        remaining_seconds = max(0, total_seconds - current_seconds)


        # Update QTimeEdit widgets
        self.current_time_edit.setTime(self.safe_qtime(current_seconds))
        self.total_time_edit.setTime(self.safe_qtime(remaining_seconds))


    def slider_was_released(self):
        """Called when the user releases the slider handle."""
        target_frame = int((self.progress_slider.value() / 1000) * self.audio_player.total_frames)
        self.audio_player.seek(target_frame)

        fs = self.audio_player.fs
        total_frames = self.audio_player.total_frames

        current_seconds = int(target_frame / fs)
        total_seconds = int(total_frames / fs)
        remaining_seconds = max(0, total_seconds - current_seconds)

        # Update QTimeEdit widgets
        self.current_time_edit.setTime(self.safe_qtime(current_seconds))
        self.total_time_edit.setTime(self.safe_qtime(remaining_seconds))

        self.no_slider_update = False

    def on_slider_clicked(self, value):
        # Convert slider value to frame position
        if hasattr(self.audio_player, 'total_frames') and self.audio_player.total_frames > 0:
            target_frame = int((value / 1000) * self.audio_player.total_frames)
            self.audio_player.seek(target_frame)

    def update_slider_position(self, frame_position):
        if self.no_slider_update:
            return
        if hasattr(self.audio_player, 'total_frames') and self.audio_player.total_frames > 0:
            # Update slider
            slider_value = int((frame_position / self.audio_player.total_frames) * 1000)

            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(slider_value)
            self.progress_slider.blockSignals(False)

            # Calculate current and total seconds
            fs = self.audio_player.fs
            total_frames = self.audio_player.total_frames

            current_seconds = int(frame_position / fs)
            total_seconds = int(total_frames / fs)
            remaining_seconds = max(0, total_seconds - current_seconds)


            # update timeedit
            if self.current_time_edit.hasFocus() and self.timeedit_update[0]: self.on_current_time_edit_started()
            if self.total_time_edit.hasFocus() and self.timeedit_update[1]: self.on_total_time_edit_started()
            
            # dynmaic minutes/hour display
            if self.timeedit_update[0]: 
                if self.safe_qtime(total_seconds).hour() > 0: self.current_time_edit.setDisplayFormat("hh:mm:ss")
                else: self.current_time_edit.setDisplayFormat("mm:ss")
                self.current_time_edit.setTime(self.safe_qtime(current_seconds))
            if self.timeedit_update[1]: 
                if self.safe_qtime(total_seconds).hour() > 0: self.total_time_edit.setDisplayFormat("hh:mm:ss")
                else: self.total_time_edit.setDisplayFormat("mm:ss")
                self.total_time_edit.setTime(self.safe_qtime(remaining_seconds))



    # --- QTimeEdit Events ---
    def on_current_time_edit_started(self):
        self.timeedit_update[0] = False
        self.tmp_qtime = self.current_time_edit.time()

    def current_time_edit_finished(self):
        """Jump to the position entered in the current_time_edit QTimeEdit."""
        # Get QTime from the editor
        qtime = self.current_time_edit.time()

        if qtime != self.tmp_qtime:
            # Convert to seconds
            seconds = qtime.hour() * 3600 + qtime.minute() * 60 + qtime.second()
            # Calculate frame position
            frame = int(seconds * self.audio_player.fs)
            # Clamp to valid range
            frame = max(0, min(frame, self.audio_player.total_frames - 1))
            # Seek to the new position
            self.audio_player.seek(frame)
        self.timeedit_update[0] = True

    def on_total_time_edit_started(self):
        self.timeedit_update[1] = False
        self.tmp_qtime = self.total_time_edit.time()
    
    def total_time_edit_edit_finished(self):
        """Jump to the position so that the entered time is the time left."""
        qtime = self.total_time_edit.time()

        if qtime != self.tmp_qtime:
            qtime = self.total_time_edit.time()
            seconds_left = qtime.hour() * 3600 + qtime.minute() * 60 + qtime.second()
            total_frames = self.audio_player.total_frames
            fs = self.audio_player.fs

            # Calculate the target frame so that this much time is left
            target_frame = total_frames - int(seconds_left * fs)
            # Clamp to valid range
            target_frame = max(0, min(target_frame, total_frames - 1))
            # Seek to the new position
            self.audio_player.seek(target_frame)
        self.timeedit_update[1] = True




    #  Load Songs 
    def open_file_or_folder(self):
        # Ask the user what they want to do
        choice = QMessageBox.question(
            self,
            "Open",
            "Do you want to open a whole folder?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        # Yes = File, No = Folder
        directory = os.path.expanduser("~/Music")
        filters = "Audio Files (*.mp3 *.wav *.flac *.ogg *.aiff);;All Files (*)"
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog

        if choice == QMessageBox.StandardButton.No:
            # Open File
            files, _ = QFileDialog.getOpenFileNames(self, "Open Audio File", directory, filters, options=options)
            if files:
                file_path = files[0]
                self.audio_player.load(file_path)
                self.song_label.setText(os.path.basename(file_path))
        else:
            # Open Folder
            folder = QFileDialog.getExistingDirectory(self, "Select Music Folder", directory, options=options)
            if folder:
                self.current_folder = folder
                audio_files = sorted(self.get_audio_files(folder))
                self.playlist = PlaylistControl(audio_files)

                self.song_list.clear()
                for file in audio_files:
                    self.song_list.addItem(os.path.basename(os.path.splitext(file)[0]))
                    self.loaded_files[os.path.basename(os.path.splitext(file)[0])] = file

                # center elements
                for i in range(self.song_list.count()):
                    self.song_list.item(i).setTextAlignment(Qt.AlignCenter)
                    self.song_list.item(i).setToolTip(self.song_list.item(i).text())


    def play_pause(self):
        if not self.progress_slider.isEnabled(): return
        if not self.is_playing:
            if not self.audio_player.isRunning():
                self.audio_player.start()
            else:
                self.audio_player.resume()
            self.is_playing = True
            self.play_pause_btn.setText("Pause")
            self.visualizer.resume()
        else:
            self.audio_player.pause()
            self.is_playing = False
            self.play_pause_btn.setText("Play")
            self.visualizer.pause()


    # --- song_list = changed song via click ---
    def handle_song_selection(self, item):
        # Get the selected song's path
        song_path = item.data(Qt.UserRole)
        if not song_path:
            # fallback for old items, try to construct path
            song_path = os.path.join(self.current_folder, item.text())
        # Update the playlist's song list and current index
        index = self.song_list.row(item)
        
        self.is_playing = True
        self.play_pause_btn.setText("Pause")

        self.playlist.go_to_song(index)
        self.progress_slider.setEnabled(True)
        self.total_time_edit.setEnabled(True)
        self.current_time_edit.setEnabled(True)

        song_path = os.path.basename(song_path)
        if song_path[-4] == ".": song_path = song_path[:-4]
        song_path =  self.loaded_files[song_path]
        self.load_new_song(song_path)
    
    # --- Playlist ---
    def toggle_playback_mode(self):
        self.current_playback_mode = (self.current_playback_mode + 1) % len(self.playback_modes)
        self.playback_mode_btn.setText(self.playback_modes[self.current_playback_mode])
        
        self.playlist.set_shuffle(False)
        if self.current_playback_mode == 0:
            self.playlist.repeat_mode = self.playlist.REPEAT_NONE
        elif self.current_playback_mode == 1:
            self.playlist.repeat_mode = self.playlist.REPEAT_ONE
        elif self.current_playback_mode == 2:
            self.playlist.repeat_mode = self.playlist.REPEAT_ALL
        elif self.current_playback_mode == 3:
            self.playlist.repeat_mode = self.playlist.REPEAT_NONE
            self.playlist.set_shuffle(True)

    def save_playlist(self):
        dlg = QFileDialog(self, "Save Playlist")
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.setNameFilter("M3U Playlist (*.m3u);;All Files (*)")
        dlg.setDefaultSuffix("m3u")
        dlg.setStyleSheet(Styles.dialog_style)
        if dlg.exec_() != QFileDialog.Accepted:
            return
        path = dlg.selectedFiles()[0]
        if not path.lower().endswith('.m3u'):
            path += '.m3u'

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                for idx in range(self.song_list.count()):
                    item = self.song_list.item(idx)
                    filename = item.text()
                    file_path = self.loaded_files[filename]
                    f.write(file_path + '\n')
            msg = QMessageBox(self)
            msg.setWindowTitle("Playlist Saved")
            msg.setIcon(QMessageBox.Information)
            msg.setText(f"Playlist saved successfully!\n\n{path}")
            msg.setStyleSheet(Styles.dialog_style)
            msg.exec_()
        except Exception as e:
            msg = QMessageBox(self)
            msg.setWindowTitle("Error")
            msg.setIcon(QMessageBox.Critical)
            msg.setText(f"Failed to save playlist:\n{e}")
            msg.setStyleSheet(Styles.dialog_style)
            msg.exec_()

    def load_playlist(self):
        from PyQt5.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox
        import os

        dlg = QFileDialog(self, "Load Playlist")
        dlg.setAcceptMode(QFileDialog.AcceptOpen)
        dlg.setNameFilter("M3U Playlist (*.m3u);;All Files (*)")
        dlg.setStyleSheet(Styles.dialog_style)
        if dlg.exec_() != QFileDialog.Accepted:
            return
        path = dlg.selectedFiles()[0]

        try:
            with open(path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            file_paths = [
                line.strip() for line in lines
                if line.strip() and not line.startswith('#')
            ]

            self.song_list.clear()
            self.loaded_files.clear()
            self.playlist.song_list.clear()

            for file_path in file_paths:
                filename = os.path.basename(file_path)
                item = QListWidgetItem(filename)
                item.setData(Qt.UserRole, file_path)
                item.setText(os.path.splitext(item.text())[0])

                self.song_list.addItem(item)
                self.loaded_files[os.path.splitext(filename)[0]] = file_path
                self.playlist.song_list.append(file_path)

            msg = QMessageBox(self)
            msg.setWindowTitle("Playlist Loaded")
            msg.setIcon(QMessageBox.Information)
            msg.setText(f"Playlist loaded successfully!\n\n{path}")
            msg.setStyleSheet(Styles.dialog_style)
            msg.exec_()
        except Exception as e:
            msg = QMessageBox(self)
            msg.setWindowTitle("Error")
            msg.setIcon(QMessageBox.Critical)
            msg.setText(f"Failed to load playlist:\n{e}")
            msg.setStyleSheet(Styles.dialog_style)
            msg.exec_()




    def song_finished(self):
        if self.audio_player.seconds_elapsed > 2: # to fast activated
            self.play_next_song()

    def play_next_song(self):
        self.on_song_list_reordered()
        self.load_new_song(self.playlist.next_song())
  
    def previous_song(self):
        self.load_new_song(self.playlist.previous_song())

    def load_new_song(self, next_song):
        if next_song is None:
            self.song_label.setText("No song loaded")
            if hasattr(self, 'audio_player'):
                self.audio_player.stop()
                return
        items = self.song_list.findItems(os.path.basename(os.path.splitext(next_song)[0]), Qt.MatchExactly)
        if items:
            self.song_list.setCurrentItem(items[0])
        else:
            index = 0
        # Stop and clean up the previous audio player if running
        if hasattr(self, 'audio_player'):
            if self.audio_player.isRunning():
                # print("Stopping previous audio thread...")
                self.audio_player.stop()
                self.audio_player.wait()
            self.audio_player.deleteLater()

        # Create a new audio player thread
        self.audio_player = AudioPlayer()
        self.audio_player.chunk_signal.connect(self.visualizer.update_visualization)
        self.audio_player.position_signal.connect(self.update_slider_position)
        self.audio_player.song_finished.connect(self.song_finished)        
        self.audio_player.load(next_song)
        

        self.audio_player.start()
        self.song_label.setText(os.path.basename(next_song))

    # -- Drag & Drop, Playlist Order ---
    def move_selected_item_up(self):
        current_row = self.song_list.currentRow()
        if current_row > 0:
            item = self.song_list.takeItem(current_row)
            self.song_list.insertItem(current_row - 1, item)
            self.song_list.setCurrentRow(current_row - 1)

    def move_selected_item_down(self):
        current_row = self.song_list.currentRow()
        if current_row < self.song_list.count() - 1:
            item = self.song_list.takeItem(current_row)
            self.song_list.insertItem(current_row + 1, item)
            self.song_list.setCurrentRow(current_row + 1)

    def on_song_list_reordered(self, parent=None, start=None, end=None, destination=None, row=None):
        
        # set current selected file
        if self.audio_player.filename is None: return
        current_filename = os.path.basename(os.path.splitext(self.audio_player.filename)[0])

        matching_item = None
        for i in range(self.song_list.count()):
            item = self.song_list.item(i)
            if item.text() == os.path.basename(os.path.splitext(current_filename)[0]):
                matching_item = item
                break

        # Select the matching item in the UI
        if matching_item is not None:
            self.song_list.setCurrentItem(matching_item)

        # select matchin song if currently played was removed
        if self.playlist.current_song() is not None and \
            self.song_list.currentItem().text() != \
            os.path.basename(os.path.splitext(self.playlist.current_song())[0]):
            print(self.song_list.currentItem().text())
            self.load_new_song(self.loaded_files[os.path.splitext(self.song_list.currentItem().text())[0]])
            self.playlist.current_index = self.playlist.song_list.index(self.audio_player.filename)
            self.playlist.go_to_song(self.playlist.current_index)

        # update playlist
        self.playlist.song_list.clear()
        for idx in range(self.song_list.count()):
            item = self.song_list.item(idx)
            filename = item.text()
            file_path = self.loaded_files[filename]
            self.playlist.song_list.append(file_path)

    # --- Right CLick Menu ---
    def show_song_list_context_menu(self, position):
        menu = QMenu()

        add_action = QAction("Add Song", self.song_list)
        remove_action = QAction("Remove Song", self.song_list)

        add_action.triggered.connect(self.add_song_to_list)
        remove_action.triggered.connect(self.remove_selected_song)

        menu.addAction(add_action)
        
        # Only enable remove if an item is selected
        if self.song_list.currentItem():
            menu.addAction(remove_action)

        menu.exec_(self.song_list.viewport().mapToGlobal(position))
        
        self.on_song_list_reordered()

    def add_song_to_list(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Songs",
            self.current_folder,
            "Audio Files (*.mp3 *.wav *.ogg *.flac);;All Files (*)"
        )
        last_item = None
        for file_path in files:
            filename = os.path.basename(file_path)
            item = QListWidgetItem(filename)
            item.setData(Qt.UserRole, file_path)
            item.setText(os.path.splitext(item.text())[0])
            item.setTextAlignment(Qt.AlignCenter)
            item.setToolTip(item.text())
            self.song_list.addItem(item)
            last_item = item
            self.loaded_files[os.path.splitext(item.text())[0]] = file_path
              # Keep reference to last added item
        # No need to append to playlist here; do it in on_song_list_reordered
        self.on_song_list_reordered()


    def remove_selected_song(self):
        item = self.song_list.currentItem()
        if item:
            row = self.song_list.row(item)
            removed_song_path = item.data(Qt.UserRole)
            is_currently_playing = (
                hasattr(self, "audio_player") and
                getattr(self.audio_player, "filename", None) == removed_song_path
            )

            self.loaded_files.pop(item.text())
            self.song_list.takeItem(row)

        self.on_song_list_reordered()









from PyQt5.QtWidgets import QStyledItemDelegate
from PyQt5.QtCore import Qt

class ElideDelegate(QStyledItemDelegate):
    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.textElideMode = Qt.ElideRight


# --- Progress Slider ---
from PyQt5.QtWidgets import QSlider, QStyle
from PyQt5.QtCore import pyqtSignal, Qt

class ClickableSlider(QSlider):
    sliderClicked = pyqtSignal(int)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)

    def is_mouse_over_handle(self, event):
        """Returns True if the mouse is over the slider handle, False otherwise."""
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        handle_rect = self.style().subControlRect(
            QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self
        )
        mouse_pos = event.pos()
        return handle_rect.contains(mouse_pos)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.is_mouse_over_handle(event):
                # Let the default slider behavior handle dragging the handle
                super().mousePressEvent(event)
            else:
                # Only trigger this if NOT over the handle
                if self.orientation() == Qt.Horizontal:
                    pos = event.x()
                    slider_length = self.width()
                else:
                    pos = event.y()
                    slider_length = self.height()

                val = QStyle.sliderValueFromPosition(
                    self.minimum(), self.maximum(), pos, slider_length, upsideDown=False
                )
                self.setValue(val)
                self.sliderClicked.emit(val)
        else:
            super().mousePressEvent(event)




from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QPainter

# --- For song title ---
class CustomLabel(QLabel):
    def __init__(self, parent=None, speed=40, step=2):
        super().__init__(parent)
        self._text = ""
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._scrollText)
        self._speed = speed  # ms per step
        self._step = step    # pixels per step
        self.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.setTextInteractionFlags(Qt.NoTextInteraction)

    def setText(self, text):
        # Clean filename before displaying
        self._text = self.clean_filename(text)
        self._offset = 0
        self.update()
        fm = self.fontMetrics()
        text_width = fm.width(self._text)
        label_width = self.width()
        if text_width > label_width:
            self._timer.start(self._speed)
        else:
            self._timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setText(self._text)  # Re-check if scrolling is needed

    @staticmethod
    def clean_filename(text):
        """
        Removes common audio file extensions and leading/trailing whitespace.
        Example: "My Song - 01.mp3" -> "My Song - 01"
        """
        # Remove extension using regex (handles .mp3, .wav, .flac, .ogg, .aac, .m4a, etc.)
        return re.sub(r'\.(mp3|wav|flac|ogg|aac|m4a|wma|aiff|alac|opus)$', '', text, flags=re.IGNORECASE).strip()

    def _scrollText(self):
        fm = self.fontMetrics()
        text_width = fm.width(self._text)
        label_width = self.width()
        if text_width <= label_width:
            self._timer.stop()
            self._offset = 0
            self.update()
            return
        self._offset += self._step
        if self._offset > text_width + 40:  # 40 pixels gap before repeating
            self._offset = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = self.fontMetrics()
        text_width = fm.width(self._text)
        label_width = self.width()
        text_height = self.height()

        if text_width <= label_width:
            # Center text if it fits
            painter.drawText(self.rect(), self.alignment(), self._text)
        else:
            # Draw scrolling text
            x = -self._offset
            y = int((text_height + fm.ascent() - fm.descent()) / 2)
            painter.drawText(x, y, self._text)
            # Draw second copy for seamless scrolling
            gap = 40  # pixels between repetitions
            painter.drawText(x + text_width + gap, y, self._text)



from PyQt5.QtWidgets import QTimeEdit
from PyQt5.QtCore import QEvent, Qt, pyqtSignal

class AdvancedTimeEdit(QTimeEdit):
    editStarted = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._editing = False
        self.installEventFilter(self)
        # Also install on all children
        for child in self.findChildren(object):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Unfocus on left click outside
        if event.type() == QEvent.MouseButtonPress:
            if self.hasFocus() and not self.underMouse():
                if event.button() == Qt.LeftButton:
                    self.clearFocus()

        # Emit editStarted on user interaction (on self or any child)
        if event.type() in (QEvent.MouseButtonPress, QEvent.KeyPress, QEvent.Wheel):
            if self.hasFocus() and not self._editing:
                self._editing = True
                self.editStarted.emit()
        elif event.type() == QEvent.FocusOut:
            self._editing = False

        return super().eventFilter(obj, event)




class Styles():
    
    timeedit = """
QTimeEdit {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #23272f, stop:1 #1e222a);
    color: #E6F0FF;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 1px;
    border-radius: 10px;
    padding: 6px 18px;           /* More horizontal padding for time */
    margin-bottom: 8px;
    border: 2px solid #3551a3;
    min-width: 90px;             /* Wider for hh:mm:ss */
    min-height: 36px;            /* A bit taller */
    qproperty-alignment: AlignCenter;
    selection-background-color: #3551a3;
    selection-color: #E6F0FF;
}
QTimeEdit:focus {
    border: 2px solid #3EC6E0;
    background: #23272f;
    color: #5A9FFF;
}
QTimeEdit::up-button, QTimeEdit::down-button {
    width: 0px;                  /* Hide spin buttons for a cleaner look */
    height: 0px;
    border: none;
}
"""

    
    label = ("""
QLabel {
    color: #E6F0FF;
    font-size: 20px;
    font-weight: 600;
    letter-spacing: 1px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #23272f, stop:1 #1e222a);
    border-radius: 10px;
    padding: 12px 24px;
    margin-bottom: 8px;
    border: 2px solid #3551a3;
}
QLabel:disabled {
    color: #5A9FFF;
    background: #23272f;
    border: 2px dashed #3551a3;
}
""")

    search_bar = ("""
        QLineEdit {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #23272f, stop:1 #1e222a);
            color: #E6F0FF;
            font-size: 16px;
            border: 2px solid #3551a3;
            border-radius: 8px;
            padding: 8px 14px;
            margin-bottom: 12px;
            selection-background-color: #3EC6E0;
            selection-color: #23272f;
        }
        QLineEdit:focus {
            border: 2px solid #426cf5;
            background: #262b36;
            color: #fff;
        }
        QLineEdit::placeholder {
            color: #5A9FFF;
            font-style: italic;
        }
    """)

    song_list = ("""
        QListWidget {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #23272f, stop:1 #1e222a);
            color: #E6F0FF;
            border-radius: 14px;
            font-size: 17px;
            padding: 0px 0px;
            outline: none;
            border: 2px solid #3551a3;
        }
        QListWidget::item {
            background: transparent;
            border: none;
            padding: 10px 6px;
            margin: 4px 0;
            border-radius: 9px;
        }
        QListWidget::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #426cf5, stop:1 #3EC6E0);
            color: #fff;
            font-weight: bold;
            border: none;
        }
        QListWidget::item:hover {
            background: rgba(90, 159, 255, 0.13);
            color: #3EC6E0;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 12px;
            margin: 8px 0 8px 0;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: #3551a3;
            min-height: 30px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover {
            background: #426cf5;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
            background: none;
            border: none;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }
    """)
    btn_style = """
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #3551a3, stop:1 #2d3a60);
    color: #E6F0FF;
    font-size: 16px;
    font-weight: 500;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    margin: 8px 0 14px 0;
    letter-spacing: 1px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #426cf5, stop:1 #3EC6E0);
    color: #fff;
}
QPushButton:pressed {
    background: #23272f;
    color: #5A9FFF;
}
"""

    dialog_style = """
QFileDialog, QMessageBox {
    background: #23272f;
    color: #E6F0FF;
    font-size: 16px;
    font-weight: 500;
}
QLabel {
    color: #E6F0FF;
}
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #3551a3, stop:1 #2d3a60);
    color: #E6F0FF;
    font-size: 16px;
    font-weight: 500;
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    margin: 8px 0 14px 0;
    letter-spacing: 1px;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #426cf5, stop:1 #3EC6E0);
    color: #fff;
}
QPushButton:pressed {
    background: #23272f;
    color: #5A9FFF;
}
"""

    progress_slider = ("""
QSlider {
    background: transparent;
    height: 32px;
}
QSlider::groove:horizontal {
    border: 2px solid #3551a3;
    height: 10px;
    background: #1e1e1e;
    border-radius: 5px;
    
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                               stop:0 #3EC6E0, stop:1 #426cf5);
    border-radius: 5px;
}
QSlider::add-page:horizontal {
    background: #1e1e1e;
    border-radius: 5px;
    
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #3551a3, stop:1 #2d3a60);
    border: 2px solid #8FC1FF;
    width: 18px;
    height: 18px;
    margin: -5px 0; /* Centers handle over groove */
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #426cf5, stop:1 #3EC6E0);
    border: 2px solid #3EC6E0;
}
QSlider::handle:horizontal:pressed {
    background: #23272f;
    border: 2px solid #5A9FFF;
}
""")







if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MusicPlayer()
    window.show()
    sys.exit(app.exec_())
