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
import tkinter as tk
from tkinterdnd2 import DND_FILES, TkinterDnD
from ui_setup import RadioShowApp

def main():
    """ The main entry point for the application. """
    root = TkinterDnD.Tk() 
    root.title("Radio Show")
    root.geometry("800x800") # A larger size for better initial view
    
    # The app will now be created from the class in ui_setup.py
    app = RadioShowApp(root) 
    root.mainloop()

# This is the standard Python entry point.
if __name__ == "__main__":
    main()
