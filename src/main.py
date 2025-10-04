import customtkinter as ctk
import json
from tkinter import colorchooser, Menu, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os

# Set appearance mode and default color theme
ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

class WatermarkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("图片水印应用")
        self.geometry("1200x800")

        self.image_paths = [] # 存储导入的图片路径
        self.current_image_index = -1
        self.original_pil_image = None # 存储原始PIL图像
        self.display_pil_image = None # 存储用于显示的PIL图像（已缩放）
        self.display_tk_image = None # 存储Tkinter PhotoImage对象
        self.watermark_color = (255, 255, 255) # Default white color
        self.watermark_font = "Arial"
        self.watermark_font_size = 48
        self.image_watermark_pil = None
        self.watermark_type = ctk.StringVar(value="text")
        self.watermark_position = "br"  # e.g., "tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br"
        self.watermark_rotation = 0
        self.output_naming_prefix = ctk.StringVar(value="wm_")
        self.output_naming_suffix = ctk.StringVar(value="")
        self.output_naming_rule = ctk.StringVar(value="prefix")
        self.jpeg_quality = ctk.IntVar(value=95)
        self.config_file = "watermark_config.json"

        # --- 创建主菜单 ---
        self.menu_bar = Menu(self)
        self.config(menu=self.menu_bar)

        # --- 文件菜单 ---
        self.file_menu = Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="导入图片", command=self.import_images)
        self.file_menu.add_command(label="导入文件夹", command=self.import_folder)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="开始处理", command=self.process_and_export_images)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="保存当前设置为模板", command=self.save_settings)
        self.file_menu.add_command(label="加载模板", command=self.load_settings)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="退出", command=self.quit_app)
        self.menu_bar.add_cascade(label="文件", menu=self.file_menu)
        
        # 帮助菜单
        self.help_menu = Menu(self.menu_bar, tearoff=0)
        self.help_menu.add_command(label="关于")
        self.menu_bar.add_cascade(label="帮助", menu=self.help_menu)

        # --- 设置主网格布局 ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- 左侧边栏 (图片列表) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsw")
        self.sidebar_frame.grid_rowconfigure(1, weight=1)
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_frame, text="图片列表", font=ctk.CTkFont(size=20, weight="bold"))
        self.sidebar_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.image_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="")
        self.image_list_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        # --- 主内容区 (图片预览) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.preview_canvas = ctk.CTkCanvas(self.main_frame, bg="gray20", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self.on_canvas_resize)


        # --- 右侧控制面板 (水印设置) ---
        self.control_frame = ctk.CTkScrollableFrame(self, width=300, label_text="水印设置")
        self.control_frame.grid(row=0, column=2, rowspan=2, sticky="nse")

        # --- 水印类型选择 ---
        self.watermark_type_frame = ctk.CTkFrame(self.control_frame)
        self.watermark_type_frame.pack(pady=10, padx=10, fill="x")
        self.watermark_type_label = ctk.CTkLabel(self.watermark_type_frame, text="类型:")
        self.watermark_type_label.pack(side="left", padx=5)
        self.text_radio = ctk.CTkRadioButton(self.watermark_type_frame, text="文本", variable=self.watermark_type, value="text", command=self.update_preview)
        self.text_radio.pack(side="left", padx=5)
        self.image_radio = ctk.CTkRadioButton(self.watermark_type_frame, text="图片", variable=self.watermark_type, value="image", command=self.update_preview)
        self.image_radio.pack(side="left", padx=5)
        
        # --- 控制面板内的选项 ---
        # 文本水印
        self.text_watermark_frame = ctk.CTkFrame(self.control_frame)
        self.text_watermark_frame.pack(pady=10, padx=10, fill="x")
        
        self.text_label = ctk.CTkLabel(self.text_watermark_frame, text="文本水印", font=ctk.CTkFont(weight="bold"))
        self.text_label.pack(pady=5, padx=10, anchor="w")
        
        self.text_entry = ctk.CTkEntry(self.text_watermark_frame, placeholder_text="输入水印文字")
        self.text_entry.pack(pady=5, padx=10, fill="x")
        self.text_entry.bind("<KeyRelease>", self.update_preview)

        # --- 字体和颜色 ---
        self.font_color_frame = ctk.CTkFrame(self.text_watermark_frame)
        self.font_color_frame.pack(pady=5, padx=10, fill="x", expand=True)

        # Font selection
        self.font_label = ctk.CTkLabel(self.font_color_frame, text="字体:")
        self.font_label.pack(side="left", padx=(0, 5))
        # A basic list of fonts that are likely to be available.
        # A more robust solution would be to query the system for available fonts.
        font_options = ["Arial", "Times New Roman", "Courier New", "Helvetica", "Verdana"]
        self.font_menu = ctk.CTkOptionMenu(self.font_color_frame, values=font_options, command=self.set_font)
        self.font_menu.pack(side="left", padx=5, expand=True, fill="x")
        self.font_menu.set("Arial")

        self.color_button = ctk.CTkButton(self.font_color_frame, text="颜色", command=self.choose_color, width=60)
        self.color_button.pack(side="left", padx=5)

        # --- Font Size ---
        self.font_size_frame = ctk.CTkFrame(self.text_watermark_frame)
        self.font_size_frame.pack(pady=5, padx=10, fill="x")
        self.font_size_label = ctk.CTkLabel(self.font_size_frame, text="字号:")
        self.font_size_label.pack(side="left", padx=(0, 5))
        self.font_size_entry = ctk.CTkEntry(self.font_size_frame, width=60)
        self.font_size_entry.insert(0, str(self.watermark_font_size))
        self.font_size_entry.pack(side="left", padx=5)
        self.font_size_entry.bind("<KeyRelease>", self.set_font_size)

        # --- 透明度 ---
        self.opacity_frame = ctk.CTkFrame(self.text_watermark_frame)
        self.opacity_frame.pack(pady=5, padx=10, fill="x")
        self.opacity_label = ctk.CTkLabel(self.opacity_frame, text="透明度:", width=60)
        self.opacity_label.pack(side="left")
        self.opacity_slider = ctk.CTkSlider(self.opacity_frame, from_=0, to=1, number_of_steps=100, command=self.update_preview)
        self.opacity_slider.set(0.5)
        self.opacity_slider.pack(side="left", fill="x", expand=True)

        # 图片水印
        self.image_watermark_frame = ctk.CTkFrame(self.control_frame)
        self.image_watermark_frame.pack(pady=10, padx=10, fill="x")
        self.image_label = ctk.CTkLabel(self.image_watermark_frame, text="图片水印", font=ctk.CTkFont(weight="bold"))
        self.image_label.pack(pady=5)
        self.image_button = ctk.CTkButton(self.image_watermark_frame, text="选择图片", command=self.select_image_watermark)
        self.image_button.pack(pady=5, padx=10, fill="x")

        self.image_opacity_slider = ctk.CTkSlider(self.image_watermark_frame, from_=0, to=1, number_of_steps=100, command=self.update_preview)
        self.image_opacity_slider.set(0.5)
        self.image_opacity_slider.pack(pady=10, padx=10, fill="x")
        
        self.image_scale_slider = ctk.CTkSlider(self.image_watermark_frame, from_=0.1, to=2.0, number_of_steps=190, command=self.update_preview)
        self.image_scale_slider.set(1.0)
        self.image_scale_slider.pack(pady=10, padx=10, fill="x")

        # --- Position & Rotation ---
        self.pos_rot_frame = ctk.CTkFrame(self.control_frame)
        self.pos_rot_frame.pack(pady=10, padx=10, fill="x")

        # Position
        self.pos_label = ctk.CTkLabel(self.pos_rot_frame, text="预设位置", font=ctk.CTkFont(weight="bold"))
        self.pos_label.pack(pady=5)

        grid_frame = ctk.CTkFrame(self.pos_rot_frame)
        grid_frame.pack()

        positions = [
            ("tl", "↖"), ("tc", "↑"), ("tr", "↗"),
            ("ml", "←"), ("mc", "·"), ("mr", "→"),
            ("bl", "↙"), ("bc", "↓"), ("br", "↘")
        ]
        for i, (pos_code, pos_text) in enumerate(positions):
            row, col = divmod(i, 3)
            btn = ctk.CTkButton(grid_frame, text=pos_text, width=40, command=lambda p=pos_code: self.set_position(p))
            btn.grid(row=row, column=col, padx=2, pady=2)

        # Rotation
        self.rot_label = ctk.CTkLabel(self.pos_rot_frame, text="旋转", font=ctk.CTkFont(weight="bold"))
        self.rot_label.pack(pady=(10, 5))
        self.rotation_slider = ctk.CTkSlider(self.pos_rot_frame, from_=0, to=360, number_of_steps=360, command=self.set_rotation)
        self.rotation_slider.set(0)
        self.rotation_slider.pack(pady=5, padx=10, fill="x")

        # --- Export Settings ---
        self.export_frame = ctk.CTkFrame(self.control_frame)
        self.export_frame.pack(pady=10, padx=10, fill="x")
        self.export_label = ctk.CTkLabel(self.export_frame, text="导出设置", font=ctk.CTkFont(weight="bold"))
        self.export_label.pack(pady=5)

        # Naming rule
        naming_frame = ctk.CTkFrame(self.export_frame)
        naming_frame.pack(fill="x", pady=2)
        ctk.CTkRadioButton(naming_frame, text="前缀:", variable=self.output_naming_rule, value="prefix").pack(side="left", padx=5)
        ctk.CTkEntry(naming_frame, textvariable=self.output_naming_prefix).pack(side="left", fill="x", expand=True)
        
        naming_frame2 = ctk.CTkFrame(self.export_frame)
        naming_frame2.pack(fill="x", pady=2)
        ctk.CTkRadioButton(naming_frame2, text="后缀:", variable=self.output_naming_rule, value="suffix").pack(side="left", padx=5)
        ctk.CTkEntry(naming_frame2, textvariable=self.output_naming_suffix).pack(side="left", fill="x", expand=True)

        ctk.CTkRadioButton(self.export_frame, text="保留原名", variable=self.output_naming_rule, value="original").pack(anchor="w", padx=15)

        # JPEG Quality
        quality_frame = ctk.CTkFrame(self.export_frame)
        quality_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(quality_frame, text="JPEG质量:").pack(side="left", padx=5)
        ctk.CTkSlider(quality_frame, from_=1, to=100, variable=self.jpeg_quality).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkLabel(quality_frame, textvariable=self.jpeg_quality, width=30).pack(side="left")

        # Export Button
        self.export_button = ctk.CTkButton(self.control_frame, text="开始处理", command=self.process_and_export_images)
        self.export_button.pack(pady=20, padx=10, fill="x")

        self.load_settings(show_message=False) # Auto-load settings on startup
        self.protocol("WM_DELETE_WINDOW", self.quit_app) # Save settings on close

    def choose_color(self):
        color_code = colorchooser.askcolor(title="选择水印颜色")
        if color_code:
            self.watermark_color = tuple(int(c) for c in color_code[0])
            self.update_preview()

    def import_images(self):
        file_types = [
            ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff"),
            ("All files", "*.*")
        ]
        files = filedialog.askopenfilenames(title="选择图片", filetypes=file_types)
        if files:
            self.add_images(list(files))
            self.update_idletasks() # Force UI update after dialog closes

    def import_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            image_files = []
            supported_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            for f in os.listdir(folder):
                if os.path.splitext(f)[1].lower() in supported_exts:
                    image_files.append(os.path.join(folder, f))
            self.add_images(image_files)
            self.update_idletasks() # Force UI update after dialog closes

    def add_images(self, paths):
        for path in paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
        self.update_image_list()
        if self.current_image_index == -1 and self.image_paths:
            self.select_image(0)

    def update_image_list(self):
        # 清空现有列表
        for widget in self.image_list_frame.winfo_children():
            widget.destroy()

        # 重新填充列表
        for i, path in enumerate(self.image_paths):
            try:
                img = Image.open(path)
                img.thumbnail((50, 50))
                thumb = ImageTk.PhotoImage(img)
                
                item_frame = ctk.CTkFrame(self.image_list_frame)
                item_frame.pack(fill="x", pady=2)

                thumb_label = ctk.CTkLabel(item_frame, image=thumb, text="")
                thumb_label.image = thumb # 保持引用
                thumb_label.pack(side="left", padx=5)

                filename = os.path.basename(path)
                name_label = ctk.CTkLabel(item_frame, text=filename, anchor="w")
                name_label.pack(side="left", fill="x", expand=True)

                item_frame.bind("<Button-1>", lambda e, index=i: self.select_image(index))
                thumb_label.bind("<Button-1>", lambda e, index=i: self.select_image(index))
                name_label.bind("<Button-1>", lambda e, index=i: self.select_image(index))

            except Exception as e:
                print(f"Error loading thumbnail for {path}: {e}")

    def on_canvas_resize(self, event=None):
        self.display_current_image(rescale=True)

    def select_image(self, index):
        if 0 <= index < len(self.image_paths):
            self.current_image_index = index
            path = self.image_paths[self.current_image_index]
            try:
                self.original_pil_image = Image.open(path).convert("RGBA")
                self.display_current_image(rescale=True)
                # 更新列表中的选中状态
                for i, child in enumerate(self.image_list_frame.winfo_children()):
                    if i == index:
                        child.configure(fg_color="gray30")
                    else:
                        child.configure(fg_color="transparent")
            except Exception as e:
                print(f"Error opening image {path}: {e}")
                self.original_pil_image = None
                self.preview_canvas.delete("all")
                self.preview_canvas.create_text(self.preview_canvas.winfo_width()/2, self.preview_canvas.winfo_height()/2, text="无法加载图片", fill="white")


    def display_current_image(self, event=None, rescale=False):
        if not self.original_pil_image:
            return

        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1: return

        # 如果需要重新缩放 (窗口大小改变或切换图片)
        if rescale:
            img_w, img_h = self.original_pil_image.size
            ratio = min(canvas_w / img_w, canvas_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)
            self.display_pil_image = self.original_pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # 复制一份用于绘制水印，避免在缩放后的图像上重复添加
        image_to_draw = self.display_pil_image.copy()

        # --- 添加水印 ---
        image_with_watermark = self.add_watermark_to_image(image_to_draw)

        # --- 更新Canvas ---
        self.display_tk_image = ImageTk.PhotoImage(image_with_watermark)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w/2, canvas_h/2, anchor="center", image=self.display_tk_image)

    def select_image_watermark(self):
        file_types = [("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="选择水印图片", filetypes=file_types)
        if path:
            try:
                self.image_watermark_pil = Image.open(path).convert("RGBA")
                self.image_watermark_pil.filename = path # Store path for saving
                self.update_preview()
            except Exception as e:
                print(f"Error opening watermark image: {e}")
                self.image_watermark_pil = None

    def add_watermark_to_image(self, image):
        watermark_type = self.watermark_type.get()
        if watermark_type == "text":
            return self.add_text_watermark(image)
        elif watermark_type == "image":
            return self.add_image_watermark(image)
        return image

    def add_text_watermark(self, image):
        watermark_text = self.text_entry.get()
        if not watermark_text:
            return image

        opacity = self.opacity_slider.get()
        alpha = int(255 * opacity)
        fill_color = self.watermark_color + (alpha,)

        # Create a temporary image for the text to calculate size and for rotation
        try:
            font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{self.watermark_font}.ttf", self.watermark_font_size)
        except IOError:
            font = ImageFont.load_default()

        try:
            text_bbox = font.getbbox(watermark_text)
            text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
        except AttributeError:
            text_w, text_h = font.getsize(watermark_text)

        txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((0, 0), watermark_text, font=font, fill=fill_color)

        # Rotate the text image
        if self.watermark_rotation != 0:
            txt_img = txt_img.rotate(self.watermark_rotation, expand=True, resample=Image.Resampling.BICUBIC)

        # Get position and paste
        wm_w, wm_h = txt_img.size
        x, y = self.get_watermark_position(image.width, image.height, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(txt_img, (x, y))

        return Image.alpha_composite(image, watermark_layer)

    def add_image_watermark(self, image):
        if not self.image_watermark_pil:
            return image

        scale = self.image_scale_slider.get()
        opacity = self.image_opacity_slider.get()
        
        wm_w, wm_h = self.image_watermark_pil.size
        new_wm_w = int(wm_w * scale)
        new_wm_h = int(wm_h * scale)
        
        if new_wm_w == 0 or new_wm_h == 0: return image

        scaled_wm = self.image_watermark_pil.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)

        if self.watermark_rotation != 0:
            scaled_wm = scaled_wm.rotate(self.watermark_rotation, expand=True, resample=Image.Resampling.BICUBIC)

        if opacity < 1.0:
            alpha = scaled_wm.split()[3]
            alpha = alpha.point(lambda p: p * opacity)
            scaled_wm.putalpha(alpha)

        wm_w, wm_h = scaled_wm.size
        x, y = self.get_watermark_position(image.width, image.height, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(scaled_wm, (x, y), scaled_wm)

        return Image.alpha_composite(image, watermark_layer)

    def update_preview(self, event=None):
        self.display_current_image(rescale=False) # 仅更新水印，不重新缩放

    def set_font(self, font_name):
        self.watermark_font = font_name
        self.update_preview()

    def set_font_size(self, event=None):
        try:
            size = int(self.font_size_entry.get())
            if size > 0:
                self.watermark_font_size = size
                self.update_preview()
        except ValueError:
            pass # Ignore non-integer input

    def set_position(self, position_code):
        self.watermark_position = position_code
        self.update_preview()

    def set_rotation(self, angle):
        self.watermark_rotation = int(angle)
        self.update_preview()

    def get_watermark_position(self, main_w, main_h, wm_w, wm_h):
        margin = 10
        pos = self.watermark_position

        if pos == "tl": x, y = margin, margin
        elif pos == "tc": x, y = (main_w - wm_w) // 2, margin
        elif pos == "tr": x, y = main_w - wm_w - margin, margin
        elif pos == "ml": x, y = margin, (main_h - wm_h) // 2
        elif pos == "mc": x, y = (main_w - wm_w) // 2, (main_h - wm_h) // 2
        elif pos == "mr": x, y = main_w - wm_w - margin, (main_h - wm_h) // 2
        elif pos == "bl": x, y = margin, main_h - wm_h - margin
        elif pos == "bc": x, y = (main_w - wm_w) // 2, main_h - wm_h - margin
        else: # br
            x, y = main_w - wm_w - margin, main_h - wm_h - margin
        
        return x, y

    def get_output_filename(self, original_path):
        directory, filename = os.path.split(original_path)
        name, ext = os.path.splitext(filename)
        
        rule = self.output_naming_rule.get()
        if rule == "prefix":
            return f"{self.output_naming_prefix.get()}{name}{ext}"
        elif rule == "suffix":
            return f"{name}{self.output_naming_suffix.get()}{ext}"
        else: # original
            return filename

    def process_and_export_images(self):
        if not self.image_paths:
            messagebox.showerror("错误", "没有导入任何图片。")
            return

        output_dir = filedialog.askdirectory(title="选择导出文件夹")
        if not output_dir:
            return

        # Prevent overwriting
        input_dirs = {os.path.dirname(p) for p in self.image_paths}
        if output_dir in input_dirs:
            messagebox.showerror("错误", "不能导出到原始图片所在的文件夹，请选择其他文件夹。")
            return

        progress_win = ctk.CTkToplevel(self)
        progress_win.title("处理中...")
        progress_win.geometry("300x100")
        progress_win.grab_set()
        
        progress_label = ctk.CTkLabel(progress_win, text="正在处理图片...")
        progress_label.pack(pady=10)
        progress_bar = ctk.CTkProgressBar(progress_win)
        progress_bar.pack(pady=10, padx=20, fill="x")
        progress_bar.set(0)

        total_images = len(self.image_paths)
        for i, path in enumerate(self.image_paths):
            try:
                original_image = Image.open(path).convert("RGBA")
                
                # Apply watermark to the full-size original image
                final_image = self.add_watermark_to_image(original_image)
                
                output_filename = self.get_output_filename(path)
                output_path = os.path.join(output_dir, output_filename)
                
                # Handle format and save
                if output_path.lower().endswith(".jpg") or output_path.lower().endswith(".jpeg"):
                    # Convert to RGB for saving as JPEG
                    final_image = final_image.convert("RGB")
                    final_image.save(output_path, "jpeg", quality=self.jpeg_quality.get())
                else:
                    # Assume PNG or other format that supports alpha
                    final_image.save(output_path)

                # Update progress
                progress = (i + 1) / total_images
                progress_bar.set(progress)
                progress_label.configure(text=f"正在处理: {i+1}/{total_images}")
                self.update_idletasks()

            except Exception as e:
                print(f"Error processing {path}: {e}")

        progress_win.destroy()
        messagebox.showinfo("完成", f"成功处理并导出了 {total_images} 张图片。")

    def quit_app(self):
        self.save_settings(show_message=False)
        self.destroy()

    def get_settings_as_dict(self):
        settings = {
            "watermark_type": self.watermark_type.get(),
            "text_content": self.text_entry.get(),
            "text_color": self.watermark_color,
            "text_font": self.watermark_font,
            "text_font_size": self.watermark_font_size,
            "text_opacity": self.opacity_slider.get(),
            "image_watermark_path": self.image_watermark_pil.filename if self.image_watermark_pil and hasattr(self.image_watermark_pil, 'filename') else None,
            "image_opacity": self.image_opacity_slider.get(),
            "image_scale": self.image_scale_slider.get(),
            "position": self.watermark_position,
            "rotation": self.watermark_rotation,
            "output_naming_rule": self.output_naming_rule.get(),
            "output_prefix": self.output_naming_prefix.get(),
            "output_suffix": self.output_naming_suffix.get(),
            "jpeg_quality": self.jpeg_quality.get(),
        }
        return settings

    def apply_settings_from_dict(self, settings):
        self.watermark_type.set(settings.get("watermark_type", "text"))
        self.text_entry.delete(0, "end")
        self.text_entry.insert(0, settings.get("text_content", ""))
        self.watermark_color = tuple(settings.get("text_color", (255, 255, 255)))
        self.watermark_font = settings.get("text_font", "Arial")
        self.font_menu.set(self.watermark_font)
        self.watermark_font_size = settings.get("text_font_size", 48)
        self.font_size_entry.delete(0, "end")
        self.font_size_entry.insert(0, str(self.watermark_font_size))
        self.opacity_slider.set(settings.get("text_opacity", 0.5))
        
        image_path = settings.get("image_watermark_path")
        if image_path and os.path.exists(image_path):
            try:
                self.image_watermark_pil = Image.open(image_path).convert("RGBA")
                self.image_watermark_pil.filename = image_path # Store path for saving
            except Exception as e:
                print(f"Failed to load watermark image from settings: {e}")
                self.image_watermark_pil = None
        else:
            self.image_watermark_pil = None

        self.image_opacity_slider.set(settings.get("image_opacity", 0.5))
        self.image_scale_slider.set(settings.get("image_scale", 1.0))
        self.watermark_position = settings.get("position", "br")
        self.watermark_rotation = settings.get("rotation", 0)
        self.rotation_slider.set(self.watermark_rotation)
        self.output_naming_rule.set(settings.get("output_naming_rule", "prefix"))
        self.output_naming_prefix.set(settings.get("output_prefix", "wm_"))
        self.output_naming_suffix.set(settings.get("output_suffix", ""))
        self.jpeg_quality.set(settings.get("jpeg_quality", 95))

        self.update_preview()

    def save_settings(self, show_message=True):
        settings = self.get_settings_as_dict()
        try:
            with open(self.config_file, "w") as f:
                json.dump(settings, f, indent=4)
            if show_message:
                messagebox.showinfo("成功", "设置已保存。")
        except Exception as e:
            if show_message:
                messagebox.showerror("错误", f"无法保存设置: {e}")

    def load_settings(self, show_message=True):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    settings = json.load(f)
                self.apply_settings_from_dict(settings)
                if show_message:
                    messagebox.showinfo("成功", "设置已加载。")
            elif show_message:
                messagebox.showwarning("未找到", "未找到配置文件。")
        except Exception as e:
            if show_message:
                messagebox.showerror("错误", f"无法加载设置: {e}")

if __name__ == "__main__":
    app = WatermarkApp()
    app.mainloop()
