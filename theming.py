# theming.py
import tkinter as tk
from tkinter import ttk
import platform
import re # For update_treeview_item_tags

LIGHT_THEME = {
    "bg": "#ECECEC", "fg": "#000000", "frame_bg": "#F0F0F0", "text_bg": "#FFFFFF", "text_fg": "#000000",
    "button_bg": "#D9D9D9", "button_fg": "#000000", "button_active_bg": "#C0C0C0",
    "select_bg": "#0078D7", "select_fg": "#FFFFFF", "tree_heading_bg": "#D9D9D9",
    "tree_even_row_bg": "#FFFFFF", "tree_odd_row_bg": "#F0F0F0", "disabled_fg": "#A0A0A0",
    "progressbar_trough": "#E0E0E0", "progressbar_bar": "#0078D7",
    "status_fg": "blue", "error_fg": "red", "success_fg": "green", "cursor_color": "#000000",
    "scrollbar_bg": "#D9D9D9", "scrollbar_trough": "#F0F0F0", "labelframe_fg": "#000000"
}

DARK_THEME = {
    "bg": "#2E2E2E", "fg": "#E0E0E0", "frame_bg": "#3C3C3C", "text_bg": "#252525", "text_fg": "#E0E0E0",
    "button_bg": "#505050", "button_fg": "#E0E0E0", "button_active_bg": "#6A6A6A",
    "select_bg": "#005A9E", "select_fg": "#E0E0E0", "tree_heading_bg": "#424242",
    "tree_even_row_bg": "#3C3C3C", "tree_odd_row_bg": "#333333", "disabled_fg": "#707070",
    "progressbar_trough": "#404040", "progressbar_bar": "#0078D7",
    "status_fg": "#ADD8E6", "error_fg": "#FF7B7B", "success_fg": "#90EE90", "cursor_color": "#FFFFFF",
    "scrollbar_bg": "#505050", "scrollbar_trough": "#3C3C3C", "labelframe_fg": "#E0E0E0"
}

def initialize_theming(app):
    detect_system_theme(app)
    # In a real app, you might load saved theme preference here
    # app.current_theme_name = saved_preference or "system"
    # app.theme_var.set(app.current_theme_name)

def detect_system_theme(app):
    system_os = platform.system()
    original_system_theme = app.system_actual_theme
    try:
        if system_os == "Windows":
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            app.system_actual_theme = "light" if value == 1 else "dark"
        elif system_os == "Darwin": # macOS
            import subprocess
            cmd = 'defaults read -g AppleInterfaceStyle'
            p = subprocess.run(cmd.split(), capture_output=True, text=True, check=False)
            if p.stdout and p.stdout.strip() == 'Dark':
                app.system_actual_theme = "dark"
            else:
                app.system_actual_theme = "light"
        else: # Linux or other
            app.system_actual_theme = "light"
    except Exception as e:
        app.logic.logger.warning(f"Could not detect system theme on {system_os}: {e}. Defaulting to light.")
        app.system_actual_theme = "light"
    
    if original_system_theme != app.system_actual_theme:
        app.logic.logger.info(f"System theme changed to: {app.system_actual_theme}")
        if app.current_theme_name == "system":
             apply_theme_settings(app)

def apply_theme_settings(app):
    if not hasattr(app, 'status_label'): # Widgets not created yet
        return

    theme_to_apply = app.current_theme_name
    if theme_to_apply == "system":
        detect_system_theme(app) 
        theme_to_apply = app.system_actual_theme
    
    app._theme_colors = LIGHT_THEME if theme_to_apply == "light" else DARK_THEME
    
    app.root.config(background=app._theme_colors["bg"])
    app.config(background=app._theme_colors["bg"]) 
    
    if hasattr(app, 'theme_menu') and app.theme_menu:
        try:
            for i in range(app.theme_menu.index(tk.END) + 1):
                app.theme_menu.entryconfigure(i, 
                                               background=app._theme_colors["bg"], 
                                               foreground=app._theme_colors["fg"],
                                               activebackground=app._theme_colors["select_bg"],
                                               activeforeground=app._theme_colors["select_fg"],
                                               selectcolor=app._theme_colors["fg"]
                                              )
        except tk.TclError as e:
            app.logic.logger.debug(f"Note: Could not fully style menu items (OS limitations likely): {e}")

    apply_standard_tk_styles(app)
    apply_ttk_styles(app)

    update_treeview_item_tags(app, app.tree)
    update_treeview_item_tags(app, app.refinement_cast_tree)
    update_treeview_item_tags(app, app.assignment_cast_tree)
    if hasattr(app, 'review_tree') and app.review_tree: # review_tree might not be initialized
        update_treeview_item_tags(app, app.review_tree)
        
    update_status_label_color(app)
    if hasattr(app, 'editor_view') and hasattr(app.editor_view, 'text_editor'): # Check if editor_view and its text_editor exist
        app.editor_view.text_editor.config(
            background=app._theme_colors["text_bg"], foreground=app._theme_colors["text_fg"],
            insertbackground=app._theme_colors["cursor_color"],
            selectbackground=app._theme_colors["select_bg"], selectforeground=app._theme_colors["select_fg"]
        )

def apply_standard_tk_styles(app):
    """Applies theme to standard Tkinter widgets."""
    c = app._theme_colors
    
    frames_to_style = [
        app.content_frame, app.status_frame, app.wizard_frame, app.wizard_view,
        app.wizard_view.upload_frame, 
        app.editor_frame, app.editor_view, app.editor_view.button_frame,
        app.cast_refinement_frame, app.cast_refinement_view,
        app.voice_assignment_frame, app.voice_assignment_view,
        app.review_frame, app.review_view
    ]
    if hasattr(app, 'cast_refinement_view'):
        frames_to_style.extend([
            app.cast_refinement_view.top_frame, app.cast_refinement_view.main_panels_frame, 
            app.cast_refinement_view.bottom_frame, app.cast_refinement_view.cast_list_outer_frame, 
            app.cast_refinement_view.results_frame
        ])
    if hasattr(app, 'voice_assignment_view'):
        frames_to_style.extend([
            app.voice_assignment_view.top_frame, app.voice_assignment_view.main_panels_frame,
            app.voice_assignment_view.bottom_frame, app.voice_assignment_view.cast_list_outer_frame,
            app.voice_assignment_view.controls_frame
        ])
    if hasattr(app, 'review_view'):
        frames_to_style.extend([
            app.review_view.top_frame, app.review_view.main_frame, 
            app.review_view.bottom_frame, app.review_view.controls_frame
        ])


    for frame in frames_to_style:
        if frame: frame.config(background=c["frame_bg"])

    for label in app._themed_tk_labels:
        if label:
            if label == app.status_label:
                label.config(background=c["frame_bg"]) 
            elif hasattr(app, 'drop_info_label') and label == app.drop_info_label:
                 label.config(background=c["frame_bg"], foreground="#808080" if c == LIGHT_THEME else "#A0A0A0")
            else:
                label.config(background=c["frame_bg"], foreground=c["fg"])
    
    for button in app._themed_tk_buttons:
        if button:
            button.config(
                background=c["button_bg"], foreground=c["button_fg"],
                activebackground=c["button_active_bg"], activeforeground=c["button_fg"],
                disabledforeground=c["disabled_fg"]
            )
    
    for labelframe in app._themed_tk_labelframes:
        if labelframe:
            labelframe.config(background=c["frame_bg"], foreground=c["labelframe_fg"])
            for child in labelframe.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(background=c["frame_bg"], foreground=c["fg"])

def apply_ttk_styles(app):
    """Applies theme to TTK widgets using ttk.Style."""
    style = ttk.Style(app.root)
    c = app._theme_colors

    style.theme_use('clam') 

    style.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["text_bg"])
    style.map(".",
              background=[('disabled', c["frame_bg"]), ('active', c["button_active_bg"])],
              foreground=[('disabled', c["disabled_fg"])])

    style.configure("TFrame", background=c["frame_bg"])
    style.configure("TLabel", background=c["frame_bg"], foreground=c["fg"])
    
    style.configure("Treeview", background=c["text_bg"], foreground=c["text_fg"], fieldbackground=c["text_bg"])
    style.map("Treeview", background=[('selected', c["select_bg"])], foreground=[('selected', c["select_fg"])])
    style.configure("Treeview.Heading", background=c["tree_heading_bg"], foreground=c["fg"], relief=tk.FLAT)
    style.map("Treeview.Heading", background=[('active', c["button_active_bg"])])

    style.configure("TCombobox", fieldbackground=c["text_bg"], background=c["button_bg"], foreground=c["text_fg"],
                    selectbackground=c["select_bg"], selectforeground=c["select_fg"], insertcolor=c["cursor_color"],
                    arrowcolor=c["fg"])
    style.map("TCombobox",
              fieldbackground=[('readonly', c["text_bg"]), ('disabled', c["frame_bg"])],
              foreground=[('disabled', c["disabled_fg"])],
              arrowcolor=[('disabled', c["disabled_fg"])])
    
    app.root.option_add("*TCombobox*Listbox.background", c["text_bg"])
    app.root.option_add("*TCombobox*Listbox.foreground", c["text_fg"])
    app.root.option_add("*TCombobox*Listbox.selectBackground", c["select_bg"])
    app.root.option_add("*TCombobox*Listbox.selectForeground", c["select_fg"])

    style.configure("TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
    style.configure("Horizontal.TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
    style.configure("Vertical.TProgressbar", troughcolor=c["progressbar_trough"], background=c["progressbar_bar"], thickness=15)
    
    if hasattr(app, 'progressbar'):
         app.progressbar.configure(style="Horizontal.TProgressbar")

    style.configure("TScrollbar", background=c["scrollbar_bg"], troughcolor=c["scrollbar_trough"], relief=tk.FLAT, arrowcolor=c["fg"])
    style.map("TScrollbar", background=[('active', c["button_active_bg"])])

def update_treeview_item_tags(app, treeview_widget):
    if not treeview_widget or not app._theme_colors: return
    c = app._theme_colors
    treeview_widget.tag_configure('oddrow', background=c["tree_odd_row_bg"])
    treeview_widget.tag_configure('evenrow', background=c["tree_even_row_bg"])

    for speaker, color in app.speaker_colors.items():
        tag_name = f"speaker_{re.sub(r'[^a-zA-Z0-9_]', '', speaker)}"
        treeview_widget.tag_configure(tag_name, foreground=color)

    children = treeview_widget.get_children('')
    for i, item_id in enumerate(children):
        current_tags = list(treeview_widget.item(item_id, 'tags'))
        current_tags = [t for t in current_tags if not t.startswith('speaker_') and t not in ('oddrow', 'evenrow')]
        current_tags.append('evenrow' if i % 2 == 0 else 'oddrow')
        try:
            speaker_val_index = 0 # Default for app.tree and both cast trees
            if treeview_widget == app.review_tree: 
                speaker_val_index = 1 
            
            item_values = treeview_widget.item(item_id, 'values')
            if item_values and len(item_values) > speaker_val_index:
                speaker_val = item_values[speaker_val_index]
                speaker_color_tag = app.get_speaker_color_tag(speaker_val) 
                if speaker_color_tag not in current_tags: current_tags.append(speaker_color_tag)
            else: # Handle cases where item might not have expected values (e.g. during deletion/repopulation)
                app.logic.logger.debug(f"Treeview item {item_id} in {treeview_widget} had unexpected values: {item_values}")

        except (IndexError, tk.TclError) as e: 
            app.logic.logger.debug(f"Error accessing item {item_id} values or tags in {treeview_widget} during theme update: {e}")
        treeview_widget.item(item_id, tags=tuple(current_tags))

def update_status_label_color(app):
    if not hasattr(app, 'status_label') or not app._theme_colors: return
    c = app._theme_colors
    current_text = app.status_label.cget("text")
    current_fg_str = str(app.status_label.cget("fg"))

    is_error = current_fg_str == LIGHT_THEME["error_fg"] or current_fg_str == DARK_THEME["error_fg"]
    is_success = current_fg_str == LIGHT_THEME["success_fg"] or current_fg_str == DARK_THEME["success_fg"]

    if "error" in current_text.lower() or "fail" in current_text.lower() or is_error:
        app.status_label.config(foreground=c["error_fg"])
    elif "success" in current_text.lower() or "complete" in current_text.lower() or is_success:
        app.status_label.config(foreground=c["success_fg"])
    else:
        app.status_label.config(foreground=c["status_fg"])
    app.status_label.config(background=c["frame_bg"])