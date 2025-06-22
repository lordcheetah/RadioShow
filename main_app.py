# main_app.py
import tkinter as tk
from tkinterdnd2 import DND_FILES, TkinterDnD
from ui_setup import RadioShowApp

def main():
    """ The main entry point for the application. """
    root = TkinterDnD.Tk() 
    root.title("Multivoice Radio Show")
    root.geometry("600x400") # Initial size
    
    # The app will now be created from the class in ui_setup.py
    app = RadioShowApp(root) 
    root.mainloop()

# This is the standard Python entry point.
if __name__ == "__main__":
    main()
