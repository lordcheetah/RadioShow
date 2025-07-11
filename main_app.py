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
    root.geometry("800x800")  # A larger size for better initial view

    # Center the window on the screen for a more professional look
    root.update_idletasks()  # Ensure window dimensions are updated
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f'{width}x{height}+{x}+{y}')

    # The app will now be created from the class in ui_setup.py
    app = RadioShowApp(root) 
    root.mainloop()

# This is the standard Python entry point.
if __name__ == "__main__":
    main()
