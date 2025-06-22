# file_operations.py
import os
import subprocess
import tempfile
from pathlib import Path
import traceback

from pydub import AudioSegment

class FileOperator:
    def __init__(self, ui, logger):
        self.ui = ui
        self.logger = logger

    def find_calibre_executable(self):
        if self.ui.calibre_exec_path and self.ui.calibre_exec_path.exists(): return True
        possible_paths = [
            Path("C:/Program Files/Calibre2/ebook-convert.exe"), 
            Path("C:/Program Files (x86)/Calibre2/ebook-convert.exe"),
            Path("C:/Program Files/Calibre/ebook-convert.exe")]
        for path in possible_paths:
            if path.exists(): self.ui.calibre_exec_path = path; return True
        return False

    def run_calibre_conversion(self):
        try:
            output_dir = Path(tempfile.gettempdir()) / "audiobook_creator"; output_dir.mkdir(exist_ok=True)
            txt_path = output_dir / f"{self.ui.ebook_path.stem}.txt"
            command = [str(self.ui.calibre_exec_path), str(self.ui.ebook_path), str(txt_path), '--enable-heuristics', '--verbose']
            result = subprocess.run(command, capture_output=True, text=True, check=False, creationflags=subprocess.CREATE_NO_WINDOW, encoding='utf-8')
            if result.returncode != 0:
                error_log_msg = f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"; 
                self.logger.error(f"Calibre conversion failed: {error_log_msg}")
                raise RuntimeError(f"Calibre failed with error:\n{error_log_msg}")
            self.ui.update_queue.put({'conversion_complete': True, 'txt_path': txt_path})
        except Exception as e:
            self.logger.error(f"Calibre conversion exception: {e}")
            self.ui.update_queue.put({'error': f"Calibre conversion failed: {str(e)}"})

    def assemble_audiobook(self, clips_info_list):
        temp_wav_path = None
        chapter_metadata_file = None
        try:
            self.logger.info(f"Starting audiobook assembly from {len(clips_info_list)} provided clip infos. Will attempt to add chapters.")
            clips_info_list.sort(key=lambda x: x['original_index'])
            
            combined_audio = AudioSegment.empty()
            silence = AudioSegment.silent(duration=250)
            chapter_markers = []
            current_cumulative_duration_ms = 0

            for clip_info in clips_info_list:
                clip_path = Path(clip_info['clip_path'])
                if clip_path.exists() and clip_path.stat().st_size > 100:
                    segment = AudioSegment.from_wav(str(clip_path))
                    original_index = clip_info['original_index']
                    if original_index < len(self.ui.analysis_result):
                        analysis_item = self.ui.analysis_result[original_index]
                        if analysis_item.get('is_chapter_start'):
                            chapter_title = analysis_item.get('chapter_title', f"Chapter {len(chapter_markers) + 1}")
                            # Clean the title: replace newlines with spaces and collapse whitespace
                            cleaned_title = " ".join(chapter_title.strip().split())
                            chapter_markers.append((current_cumulative_duration_ms, cleaned_title))
                            self.logger.info(f"Detected chapter '{cleaned_title}' at {current_cumulative_duration_ms}ms.")
                    combined_audio += segment + silence
                    current_cumulative_duration_ms += len(segment) + len(silence)

            if len(combined_audio) == 0: raise ValueError("No valid audio data was generated.")

            temp_wav_path = self.ui.output_dir / f"{self.ui.ebook_path.stem}_temp.wav"
            combined_audio.export(str(temp_wav_path), format="wav")

            final_audio_path = self.ui.output_dir / f"{self.ui.ebook_path.stem}_audiobook.m4b"

            if chapter_markers:
                chapter_metadata_file = self.ui.output_dir / f"{self.ui.ebook_path.stem}_chapters.txt"
                with open(chapter_metadata_file, 'w', encoding='utf-8') as f:
                    f.write(';FFMETADATA1\n')
                    for start_ms, title in chapter_markers:
                        f.write(f'[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\ntitle={title}\n\n')

            # Re-ordered FFmpeg command: all inputs first, then all output options.
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(temp_wav_path), # Input 0: audio
            ]
            if chapter_metadata_file:
                # Input 1: chapters. The -f option applies to the *next* -i option.
                ffmpeg_cmd.extend(['-f', 'ffmetadata', '-i', str(chapter_metadata_file)])
            
            # Now add all output options
            ffmpeg_cmd.extend([
                '-c:a', 'aac',      # Set audio codec to AAC for M4B
                '-b:a', '128k',     # Set audio bitrate
            ])

            # If we have a chapter file, map its metadata to the output.
            if chapter_metadata_file:
                ffmpeg_cmd.extend(['-map_metadata', '1'])

            # Add general metadata tags
            ffmpeg_cmd.extend([
                '-metadata', f'artist=Audiobook Creator',
                '-metadata', f'album={self.ui.ebook_path.stem}',
                '-metadata', f'title={self.ui.ebook_path.stem} Audiobook',
            ])
            
            # Finally, add the output file path
            ffmpeg_cmd.append(str(final_audio_path))

            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
            self.ui.update_queue.put({'assembly_complete': True, 'final_path': final_audio_path})
        except Exception as e:
            detailed_error = traceback.format_exc()
            self.logger.error(f"Critical error during audiobook assembly: {detailed_error}")
            self.ui.update_queue.put({'error': f"A critical error occurred during assembly:\n\n{detailed_error}"})
        finally:
            if temp_wav_path and temp_wav_path.exists():
                try:
                    os.remove(temp_wav_path)
                    self.logger.info(f"Cleaned up temporary WAV file: {temp_wav_path}")
                except Exception as e:
                    self.logger.warning(f"Could not delete temporary WAV file {temp_wav_path}: {e}")
            if chapter_metadata_file and chapter_metadata_file.exists():
                try:
                    os.remove(chapter_metadata_file)
                    self.logger.info(f"Cleaned up temporary chapter metadata file: {chapter_metadata_file}")
                except Exception as e:
                    self.logger.warning(f"Could not delete temporary chapter metadata file {chapter_metadata_file}: {e}")