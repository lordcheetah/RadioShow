import rtx50_compat
# main_app.py
# -*- coding: utf-8 -*-
"""
main_app.py

This script serves as the main entry point for the Multivoice Radio Show application.
It initializes the Tkinter root window and launches the main application class,
which handles the UI and core logic for converting ebooks into multi-voice audiobooks.

Authors:
    - James Guenther
    - VS Code with Gemini
"""
from tkinterdnd2 import TkinterDnD
from ui_setup import RadioShowApp

def main():
    """ The main entry point for the application. """
    root = TkinterDnD.Tk() 
    root.title("Radio Show")

    # Center the window on the screen for a more professional look
    width = 800
    height = 800
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width // 2) - (width // 2)
    y = (screen_height // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')

    # The app will now be created from the class in ui_setup.py
    app = RadioShowApp(root) 
    root.mainloop()

# This is the standard Python entry point.
if __name__ == "__main__":
    main()
