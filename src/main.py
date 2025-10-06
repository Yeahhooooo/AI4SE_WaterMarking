import customtkinter as ctk
import json
import threading
import queue
import time
import os
from tkinter import colorchooser, Menu, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw, ImageFont

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
        self.output_naming_suffix = ctk.StringVar(value="_watermark")
        self.output_naming_rule = ctk.StringVar(value="suffix")
        self.jpeg_quality = ctk.IntVar(value=95)
        self.config_file = "watermark_config.json"
        self._debounce_job = None # For debouncing UI updates
        
        # --- 模板管理系统 ---
        self.templates_dir = "templates"
        self.current_template_name = None
        self.template_extension = ".json"
        
        # --- 输出路径设置 ---
        self.output_directory = ctk.StringVar(value="")  # 输出目录路径
        
        # --- 多线程组件 ---
        self.preview_queue = queue.Queue()
        self.thumbnail_queue = queue.Queue()
        self.preview_thread_pool = []
        self.is_closing = False
        
        # --- 性能优化缓存 ---
        self.watermark_cache = {}  # 缓存已生成的水印
        self.last_watermark_params = None  # 上次水印参数
        self.base_watermark_image = None  # 基础水印图像（无位置信息）
        self.current_processing_id = 0  # 当前处理ID，用于取消过期任务
        
        # --- 拖拽功能相关 ---
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.custom_watermark_position = None  # 自定义位置 (x, y) 相对于图片坐标
        self.watermark_bounds = None  # 水印边界框，用于拖拽检测
        
        # 启动队列监听
        self.start_queue_processing()

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
        self.sidebar_frame.grid_rowconfigure(2, weight=1)
        
        self.sidebar_title = ctk.CTkLabel(self.sidebar_frame, text="图片列表", font=ctk.CTkFont(size=20, weight="bold"))
        self.sidebar_title.grid(row=0, column=0, padx=20, pady=(20, 10))

        # 添加导入按钮
        self.import_buttons_frame = ctk.CTkFrame(self.sidebar_frame)
        self.import_buttons_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        
        self.import_images_btn = ctk.CTkButton(self.import_buttons_frame, text="导入图片", command=self.import_images)
        self.import_images_btn.pack(side="left", padx=(0, 5), expand=True, fill="x")
        
        self.import_folder_btn = ctk.CTkButton(self.import_buttons_frame, text="导入文件夹", command=self.import_folder)
        self.import_folder_btn.pack(side="left", padx=(5, 0), expand=True, fill="x")

        self.image_list_frame = ctk.CTkScrollableFrame(self.sidebar_frame, label_text="")
        self.image_list_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")

        # --- 主内容区 (图片预览) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.preview_canvas = ctk.CTkCanvas(self.main_frame, bg="gray20", highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self.on_canvas_resize)
        
        # 添加鼠标事件绑定用于拖拽水印
        self.preview_canvas.bind("<Button-1>", self.on_canvas_click)
        self.preview_canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_canvas_release)


        # --- 右侧控制面板 (水印设置) ---
        self.control_frame = ctk.CTkScrollableFrame(self, width=300, label_text="水印设置")
        self.control_frame.grid(row=0, column=2, rowspan=2, sticky="nse")

        # --- 水印类型选择 ---
        self.watermark_type_frame = ctk.CTkFrame(self.control_frame)
        self.watermark_type_frame.pack(pady=10, padx=10, fill="x")
        self.watermark_type_label = ctk.CTkLabel(self.watermark_type_frame, text="类型:")
        self.watermark_type_label.pack(side="left", padx=5)
        self.text_radio = ctk.CTkRadioButton(self.watermark_type_frame, text="文本", variable=self.watermark_type, value="text", command=self.on_watermark_type_changed)
        self.text_radio.pack(side="left", padx=5)
        self.image_radio = ctk.CTkRadioButton(self.watermark_type_frame, text="图片", variable=self.watermark_type, value="image", command=self.on_watermark_type_changed)
        self.image_radio.pack(side="left", padx=5)
        
        # --- 控制面板内的选项 ---
        # 文本水印
        self.text_watermark_frame = ctk.CTkFrame(self.control_frame)
        self.text_watermark_frame.pack(pady=10, padx=10, fill="x")
        
        self.text_label = ctk.CTkLabel(self.text_watermark_frame, text="文本水印", font=ctk.CTkFont(weight="bold"))
        self.text_label.pack(pady=5, padx=10, anchor="w")
        
        self.text_entry = ctk.CTkEntry(self.text_watermark_frame, placeholder_text="输入水印文字")
        self.text_entry.pack(pady=5, padx=10, fill="x")
        self.text_entry.bind("<KeyRelease>", self.debounced_update_preview)

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
        self.opacity_slider = ctk.CTkSlider(self.opacity_frame, from_=0, to=1, number_of_steps=100, command=self.debounced_update_preview)
        self.opacity_slider.set(0.5)
        self.opacity_slider.pack(side="left", fill="x", expand=True)

        # 图片水印
        self.image_watermark_frame = ctk.CTkFrame(self.control_frame)
        self.image_watermark_frame.pack(pady=10, padx=10, fill="x")
        self.image_label = ctk.CTkLabel(self.image_watermark_frame, text="图片水印", font=ctk.CTkFont(weight="bold"))
        self.image_label.pack(pady=5)
        self.image_button = ctk.CTkButton(self.image_watermark_frame, text="选择水印图片", command=self.select_image_watermark)
        self.image_button.pack(pady=5, padx=10, fill="x")

        # --- 图片透明度 ---
        self.image_opacity_label = ctk.CTkLabel(self.image_watermark_frame, text="透明度:")
        self.image_opacity_label.pack(pady=(10, 0), padx=10, anchor="w")
        self.image_opacity_slider = ctk.CTkSlider(self.image_watermark_frame, from_=0, to=1, number_of_steps=100, command=self.debounced_update_preview)
        self.image_opacity_slider.set(0.5)
        self.image_opacity_slider.pack(pady=(0, 10), padx=10, fill="x")
        
        # --- 图片大小 ---
        self.image_scale_label = ctk.CTkLabel(self.image_watermark_frame, text="大小:")
        self.image_scale_label.pack(pady=(0, 0), padx=10, anchor="w")
        self.image_scale_slider = ctk.CTkSlider(self.image_watermark_frame, from_=0.1, to=2.0, number_of_steps=190, command=self.debounced_update_preview)
        self.image_scale_slider.set(1.0)
        self.image_scale_slider.pack(pady=(0, 10), padx=10, fill="x")

        # --- Position & Rotation ---
        self.pos_rot_frame = ctk.CTkFrame(self.control_frame)
        self.pos_rot_frame.pack(pady=10, padx=10, fill="x")

        # Position
        self.pos_label = ctk.CTkLabel(self.pos_rot_frame, text="预设位置", font=ctk.CTkFont(weight="bold"))
        self.pos_label.pack(pady=5)
        
        # 添加拖拽提示
        self.drag_hint_label = ctk.CTkLabel(self.pos_rot_frame, text="💡 提示：在预览窗口中可直接拖拽水印调整位置", 
                                          font=ctk.CTkFont(size=11), text_color="gray")
        self.drag_hint_label.pack(pady=(0, 5))

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

        # Output Directory
        output_dir_frame = ctk.CTkFrame(self.export_frame)
        output_dir_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(output_dir_frame, text="输出路径:").pack(side="left", padx=5)
        
        # 显示当前路径的标签（可点击更改）
        self.output_path_label = ctk.CTkLabel(output_dir_frame, text="点击选择输出文件夹", 
                                            fg_color="gray25", corner_radius=6, cursor="hand2")
        self.output_path_label.pack(side="left", fill="x", expand=True, padx=5)
        self.output_path_label.bind("<Button-1>", lambda e: self.choose_output_directory())
        
        # 更改路径按钮
        self.change_output_btn = ctk.CTkButton(output_dir_frame, text="浏览", width=60, 
                                             command=self.choose_output_directory)
        self.change_output_btn.pack(side="right", padx=5)

        # JPEG Quality
        quality_frame = ctk.CTkFrame(self.export_frame)
        quality_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(quality_frame, text="JPEG质量:").pack(side="left", padx=5)
        ctk.CTkSlider(quality_frame, from_=1, to=100, variable=self.jpeg_quality).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkLabel(quality_frame, textvariable=self.jpeg_quality, width=30).pack(side="left")

        # --- Template Management ---
        self.template_frame = ctk.CTkFrame(self.control_frame)
        self.template_frame.pack(pady=10, padx=10, fill="x")
        self.template_label = ctk.CTkLabel(self.template_frame, text="水印模板", font=ctk.CTkFont(weight="bold"))
        self.template_label.pack(pady=5)

        # Template selection
        template_select_frame = ctk.CTkFrame(self.template_frame)
        template_select_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(template_select_frame, text="选择模板:").pack(side="left", padx=5)
        self.template_combobox = ctk.CTkComboBox(template_select_frame, values=["<无模板>"], 
                                               command=self.load_template_by_name, state="readonly")
        self.template_combobox.pack(side="left", fill="x", expand=True, padx=5)
        self.template_combobox.set("<无模板>")

        # Template management buttons
        template_buttons_frame = ctk.CTkFrame(self.template_frame)
        template_buttons_frame.pack(fill="x", pady=5)
        
        self.save_template_btn = ctk.CTkButton(template_buttons_frame, text="保存模板", 
                                             command=self.save_new_template, width=80)
        self.save_template_btn.pack(side="left", padx=2, expand=True, fill="x")
        
        self.rename_template_btn = ctk.CTkButton(template_buttons_frame, text="重命名", 
                                               command=self.rename_template, width=80)
        self.rename_template_btn.pack(side="left", padx=2, expand=True, fill="x")
        
        self.delete_template_btn = ctk.CTkButton(template_buttons_frame, text="删除", 
                                               command=self.delete_template, width=80)
        self.delete_template_btn.pack(side="left", padx=2, expand=True, fill="x")

        # Auto-load settings
        auto_load_frame = ctk.CTkFrame(self.template_frame)
        auto_load_frame.pack(fill="x", pady=5)
        self.auto_load_last = ctk.BooleanVar(value=True)
        self.auto_load_checkbox = ctk.CTkCheckBox(auto_load_frame, text="启动时自动加载上次设置", 
                                                variable=self.auto_load_last)
        self.auto_load_checkbox.pack(side="left", padx=5)

        # Export Button
        self.export_button = ctk.CTkButton(self.control_frame, text="开始处理并导出", command=self.process_and_export_images)
        self.export_button.pack(pady=20, padx=10, fill="x")

        self.init_template_system() # Initialize template system
        self.load_settings(show_message=False) # Auto-load settings on startup
        self.load_last_settings_or_default_template() # Auto-load last template if enabled
        self.on_watermark_type_changed() # Initialize UI visibility based on default type
        self.protocol("WM_DELETE_WINDOW", self.quit_app) # Save settings on close

    def start_queue_processing(self):
        """启动队列处理，定期检查后台任务完成情况"""
        self.process_queues()
        
    def start_ui_refresh_timer(self):
        """启动UI刷新定时器，确保事件循环始终活跃"""
        pass  # 简化：移除复杂的UI刷新逻辑
        
    def process_queues(self):
        """处理队列中的完成任务"""
        try:
            # 处理预览队列
            while not self.preview_queue.empty():
                try:
                    callback, result = self.preview_queue.get_nowait()
                    callback(result)
                except queue.Empty:
                    break
                    
            # 处理缩略图队列
            while not self.thumbnail_queue.empty():
                try:
                    callback, result = self.thumbnail_queue.get_nowait()
                    callback(result)
                except queue.Empty:
                    break
                    
        except Exception as e:
            print(f"Queue processing error: {e}")
            
        # 如果应用没有关闭，继续处理队列
        if not self.is_closing:
            self.after(50, self.process_queues)

    def async_generate_preview(self, image_data, watermark_params, callback):
        """在后台线程生成预览图像"""
        def worker():
            try:
                # 解包参数
                original_image, canvas_size, rescale = image_data
                watermark_type, text_content, font_params, image_watermark, position, rotation, opacity = watermark_params
                
                # 计算显示尺寸和缩放比例
                preview_scale = 1.0
                if rescale:
                    canvas_w, canvas_h = canvas_size
                    img_w, img_h = original_image.size
                    ratio = min(canvas_w / img_w, canvas_h / img_h)
                    new_w = int(img_w * ratio)
                    new_h = int(img_h * ratio)
                    display_image = original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    preview_scale = ratio  # 记录预览缩放比例
                else:
                    display_image = original_image
                
                # 复制用于水印处理
                image_to_draw = display_image.copy()
                
                # 添加水印（调整水印参数以匹配预览缩放）
                if watermark_type == "text" and text_content:
                    # 调整字体大小以匹配预览缩放
                    scaled_font_params = self.scale_font_params_for_preview(font_params, preview_scale)
                    image_with_watermark = self.generate_text_watermark(
                        image_to_draw, text_content, scaled_font_params, position, rotation, opacity
                    )
                elif watermark_type == "image" and image_watermark:
                    # 调整图片水印尺寸以匹配预览缩放
                    base_scale = self.image_scale_slider.get()
                    preview_adjusted_scale = base_scale * preview_scale
                    img_opacity = self.image_opacity_slider.get()
                    image_with_watermark = self.generate_image_watermark(
                        image_to_draw, image_watermark, (preview_adjusted_scale, img_opacity), position, rotation
                    )
                else:
                    image_with_watermark = image_to_draw
                
                # 将PIL图像结果放入队列（不在这里转换为Tkinter格式）
                self.preview_queue.put((callback, (image_with_watermark, display_image)))
                
            except Exception as e:
                print(f"Preview generation error: {e}")
                self.preview_queue.put((callback, None))
        
        # 启动后台线程
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def scale_font_params_for_preview(self, font_params, scale):
        """为预览调整字体参数，使字体大小与预览缩放比例匹配"""
        font_name, font_size, color = font_params
        # 将字体大小按预览比例缩放，但确保最小字体大小为8
        scaled_font_size = max(8, int(font_size * scale))
        return (font_name, scaled_font_size, color)
    
    def adjust_watermark_params_for_preview(self, params, scale):
        """为预览调整水印参数，确保水印大小与预览缩放匹配"""
        adjusted_params = params.copy()
        
        if params['type'] == 'text':
            # 调整字体参数
            adjusted_params['font'] = self.scale_font_params_for_preview(params['font'], scale)
        elif params['type'] == 'image':
            # 调整图片水印缩放
            original_scale = params['scale']
            adjusted_params['scale'] = original_scale * scale
            
        return adjusted_params

    def async_generate_thumbnail(self, image_path, callback):
        """在后台线程生成缩略图"""
        def worker():
            try:
                img = Image.open(image_path)
                img.thumbnail((50, 50))
                # 使用CTkImage以支持高DPI显示
                thumb = ctk.CTkImage(light_image=img, size=(50, 50))
                self.thumbnail_queue.put((callback, (thumb, image_path)))
            except Exception as e:
                print(f"Thumbnail generation error: {e}")
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def generate_text_watermark(self, image, text_content, font_params, position, rotation, opacity):
        """后台线程安全的文本水印生成"""
        font_name, font_size, color = font_params
        alpha = int(255 * opacity)
        fill_color = color + (alpha,)

        try:
            font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{font_name}.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        try:
            text_bbox = font.getbbox(text_content)
            # 考虑bbox可能的负偏移
            left, top, right, bottom = text_bbox
            text_w, text_h = right - left, bottom - top
        except AttributeError:
            text_w, text_h = font.getsize(text_content)
            left, top = 0, 0

        txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)
        # 调整文本位置以补偿bbox偏移
        draw.text((-left, -top), text_content, font=font, fill=fill_color)

        if rotation != 0:
            txt_img = txt_img.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

        wm_w, wm_h = txt_img.size
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, position)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(txt_img, (x, y))

        return Image.alpha_composite(image, watermark_layer)

    def generate_image_watermark(self, image, watermark_image, params, position, rotation):
        """后台线程安全的图片水印生成"""
        scale, opacity = params
        
        wm_w, wm_h = watermark_image.size
        new_wm_w = int(wm_w * scale)
        new_wm_h = int(wm_h * scale)
        
        if new_wm_w == 0 or new_wm_h == 0:
            return image

        scaled_wm = watermark_image.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)

        if rotation != 0:
            scaled_wm = scaled_wm.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

        if opacity < 1.0:
            alpha = scaled_wm.split()[3]
            alpha = alpha.point(lambda p: p * opacity)
            scaled_wm.putalpha(alpha)

        wm_w, wm_h = scaled_wm.size
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, position)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(scaled_wm, (x, y), scaled_wm)

        return Image.alpha_composite(image, watermark_layer)

    def calculate_watermark_position(self, main_w, main_h, wm_w, wm_h, position):
        """计算水印位置（支持自定义位置），坐标基于当前图片尺寸"""
        # 如果有自定义位置，需要转换坐标
        if self.custom_watermark_position is not None:
            custom_x, custom_y = self.custom_watermark_position
            
            # 如果当前处理的图片不是原始图片（比如预览图片），需要转换坐标
            if hasattr(self, 'original_pil_image') and self.original_pil_image:
                original_w, original_h = self.original_pil_image.size
                
                # 如果尺寸不同，说明是预览图片，需要按比例转换
                if main_w != original_w or main_h != original_h:
                    scale_x = main_w / original_w
                    scale_y = main_h / original_h
                    
                    x = int(custom_x * scale_x)
                    y = int(custom_y * scale_y)
                else:
                    # 尺寸相同，直接使用自定义位置
                    x, y = int(custom_x), int(custom_y)
            else:
                x, y = int(custom_x), int(custom_y)
            
            # 确保水印不超出图片边界
            x = max(0, min(x, main_w - wm_w))
            y = max(0, min(y, main_h - wm_h))
            return x, y
        
        # 否则使用预设位置
        margin = 10

        if position == "tl": x, y = margin, margin
        elif position == "tc": x, y = (main_w - wm_w) // 2, margin
        elif position == "tr": x, y = main_w - wm_w - margin, margin
        elif position == "ml": x, y = margin, (main_h - wm_h) // 2
        elif position == "mc": x, y = (main_w - wm_w) // 2, (main_h - wm_h) // 2
        elif position == "mr": x, y = main_w - wm_w - margin, (main_h - wm_h) // 2
        elif position == "bl": x, y = margin, main_h - wm_h - margin
        elif position == "bc": x, y = (main_w - wm_w) // 2, main_h - wm_h - margin
        else: # br
            x, y = main_w - wm_w - margin, main_h - wm_h - margin
        
        return x, y
        
        return x, y

    def clear_watermark_cache(self):
        """清理水印缓存"""
        self.watermark_cache.clear()
        self.base_watermark_image = None
        self.last_watermark_params = None
        # 清除自定义位置
        self.custom_watermark_position = None
        self.watermark_bounds = None

    def choose_color(self):
        """优化的颜色选择，减少UI阻塞"""
        color_code = colorchooser.askcolor(title="选择水印颜色")
        # If the user selects a color, color_code will be a tuple like ((r, g, b), '#rrggbb')
        # If the user cancels, it will be (None, None).
        if color_code and color_code[0]:
            self.watermark_color = tuple(int(c) for c in color_code[0])
            self.color_button.configure(fg_color=color_code[1])
            # 延迟清理缓存，避免立即重新生成
            self.after_idle(self.clear_watermark_cache)
            self.debounced_update_preview()
    
    def choose_output_directory(self):
        """选择输出目录"""
        # 如果已经有设置的目录，从该目录开始选择
        initial_dir = self.output_directory.get() if self.output_directory.get() else os.path.expanduser("~/Desktop")
        
        selected_dir = filedialog.askdirectory(
            title="选择输出文件夹",
            initialdir=initial_dir
        )
        
        if selected_dir:
            self.output_directory.set(selected_dir)
            self.update_output_path_display()
    
    def update_output_path_display(self):
        """更新输出路径显示"""
        path = self.output_directory.get()
        if path:
            # 显示路径，如果太长则显示省略版本
            display_path = path
            if len(display_path) > 40:
                # 显示开头和结尾部分
                display_path = f"...{display_path[-37:]}"
            self.output_path_label.configure(text=display_path, text_color="white")
        else:
            self.output_path_label.configure(text="点击选择输出文件夹", text_color="gray60")

    def import_images_with_refresh(self):
        """简化的图片导入，依赖响应性回调包装器"""
        self.import_images()

    def import_folder_with_refresh(self):
        """简化的文件夹导入，依赖响应性回调包装器"""
        self.import_folder()

    def import_images(self):
        print("Importing images...")
        file_types = [
            ("Image files", "*.jpg *.jpeg *.png *.bmp *.tiff"),
            ("All files", "*.*")
        ]
        files = filedialog.askopenfilenames(title="选择图片", filetypes=file_types)
        if files:
            # Use self.after to schedule the update, which is more robust on macOS
            # to prevent UI freezes after the dialog closes.
            self.after(100, lambda: self.add_images(list(files)))

    def import_folder(self):
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            image_files = []
            supported_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
            for f in os.listdir(folder):
                if os.path.splitext(f)[1].lower() in supported_exts:
                    image_files.append(os.path.join(folder, f))
            # Use self.after for the same reason as above
            self.after(100, lambda: self.add_images(image_files))

    def add_images(self, paths):
        for path in paths:
            if path not in self.image_paths:
                self.image_paths.append(path)
        self.update_image_list()
        if self.current_image_index == -1 and self.image_paths:
            self.select_image(0)

    def update_image_list(self):
        """异步更新图片列表和缩略图"""
        # 清空现有列表
        for widget in self.image_list_frame.winfo_children():
            widget.destroy()

        # 为每个图片创建占位框架并异步生成缩略图
        for i, path in enumerate(self.image_paths):
            self.create_image_list_item(i, path)

    def create_image_list_item(self, index, path):
        """创建图片列表项，包含异步缩略图"""
        item_frame = ctk.CTkFrame(self.image_list_frame)
        item_frame.pack(fill="x", pady=2)

        # 创建占位缩略图标签
        thumb_label = ctk.CTkLabel(item_frame, text="载入中...", width=50, height=50)
        thumb_label.pack(side="left", padx=5)

        filename = os.path.basename(path)
        name_label = ctk.CTkLabel(item_frame, text=filename, anchor="w")
        name_label.pack(side="left", fill="x", expand=True)

        # 绑定点击事件
        item_frame.bind("<Button-1>", lambda e, i=index: self.select_image(i))
        thumb_label.bind("<Button-1>", lambda e, i=index: self.select_image(i))
        name_label.bind("<Button-1>", lambda e, i=index: self.select_image(i))

        # 异步生成缩略图
        self.async_generate_thumbnail(path, lambda result: self.on_thumbnail_ready(result, thumb_label))

    def on_thumbnail_ready(self, result, thumb_label):
        """缩略图生成完成的回调"""
        if result is None:
            thumb_label.configure(text="错误")
            return
            
        thumb, path = result
        try:
            # 使用CTkImage时直接设置image参数
            thumb_label.configure(image=thumb, text="")
        except Exception as e:
            print(f"Error updating thumbnail: {e}")
            thumb_label.configure(text="错误")

    def on_canvas_resize(self, event=None):
        self.display_current_image(rescale=True)
    
    def on_canvas_click(self, event):
        """处理Canvas点击事件，开始拖拽检测"""
        if not self.original_pil_image or not self.display_pil_image:
            return
            
        # 获取点击位置（Canvas坐标）
        click_x, click_y = event.x, event.y
        
        # 检查是否点击在水印区域内
        if self.is_click_on_watermark(click_x, click_y):
            self.is_dragging = True
            self.drag_start_x = click_x
            self.drag_start_y = click_y
            self.preview_canvas.config(cursor="hand2")  # 改变鼠标样式
            
    def on_canvas_drag(self, event):
        """处理Canvas拖拽事件"""
        if not self.is_dragging:
            return
            
        # 计算拖拽偏移量
        delta_x = event.x - self.drag_start_x
        delta_y = event.y - self.drag_start_y
        
        # 将Canvas坐标转换为图片坐标并更新水印位置
        self.update_watermark_position_from_drag(delta_x, delta_y)
        
        # 更新拖拽起始点
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        
    def on_canvas_release(self, event):
        """处理Canvas鼠标释放事件，结束拖拽"""
        if self.is_dragging:
            self.is_dragging = False
            self.preview_canvas.config(cursor="")  # 恢复鼠标样式
            
            # 将预览坐标转换为原始图片坐标并保存
            if hasattr(self, 'preview_watermark_position') and self.preview_watermark_position:
                preview_x, preview_y = self.preview_watermark_position
                
                # 转换为原始图片坐标
                if self.display_pil_image and self.original_pil_image:
                    preview_w, preview_h = self.display_pil_image.size
                    original_w, original_h = self.original_pil_image.size
                    scale_x = original_w / preview_w
                    scale_y = original_h / preview_h
                    
                    # 转换坐标
                    original_x = preview_x * scale_x
                    original_y = preview_y * scale_y
                    
                    # 计算原始图片上的水印大小，确保水印不超出边界
                    watermark_params = self.get_current_watermark_params()
                    original_wm_w, original_wm_h = self.estimate_watermark_size_for_original(watermark_params)
                    
                    # 确保水印在原始图片边界内
                    original_x = max(0, min(original_x, original_w - original_wm_w))
                    original_y = max(0, min(original_y, original_h - original_wm_h))
                    
                    # 保存为自定义位置
                    self.custom_watermark_position = (original_x, original_y)
                
                # 清除临时预览位置
                delattr(self, 'preview_watermark_position')
            
            # 触发最终的预览更新
            self.debounced_update_preview()
            
    def is_click_on_watermark(self, canvas_x, canvas_y):
        """检查点击位置是否在水印区域内"""
        if not self.display_pil_image or not self.watermark_bounds:
            return False
            
        # 获取Canvas和图片的尺寸信息
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        img_w, img_h = self.display_pil_image.size
        
        # 计算图片在Canvas中的位置（居中显示）
        img_canvas_x = (canvas_w - img_w) // 2
        img_canvas_y = (canvas_h - img_h) // 2
        
        # 将Canvas坐标转换为图片坐标
        img_x = canvas_x - img_canvas_x
        img_y = canvas_y - img_canvas_y
        
        # 检查是否在图片范围内
        if img_x < 0 or img_x >= img_w or img_y < 0 or img_y >= img_h:
            return False
            
        # 检查是否在水印边界内
        wm_x, wm_y, wm_w, wm_h = self.watermark_bounds
        return (wm_x <= img_x <= wm_x + wm_w and wm_y <= img_y <= wm_y + wm_h)
        
    def update_watermark_position_from_drag(self, delta_x, delta_y):
        """根据拖拽偏移量更新水印位置，在预览坐标系统中工作"""
        if not self.display_pil_image or not self.original_pil_image:
            return
            
        # 在拖拽过程中，我们在预览坐标系统中工作
        # 获取当前水印在预览图片上的位置
        if hasattr(self, 'preview_watermark_position') and self.preview_watermark_position:
            current_x, current_y = self.preview_watermark_position
        else:
            # 如果有原始坐标的自定义位置，转换为预览坐标
            if self.custom_watermark_position:
                orig_x, orig_y = self.custom_watermark_position
                # 转换为预览坐标
                preview_w, preview_h = self.display_pil_image.size
                original_w, original_h = self.original_pil_image.size
                scale_x = preview_w / original_w
                scale_y = preview_h / original_h
                current_x = orig_x * scale_x
                current_y = orig_y * scale_y
            else:
                # 从预设位置计算初始位置（基于预览图片尺寸）
                current_x, current_y = self.get_current_watermark_preview_position()
            
        # 更新预览位置
        new_x = current_x + delta_x
        new_y = current_y + delta_y
        
        # 确保水印不超出预览图片边界
        watermark_params = self.get_current_watermark_params()
        
        # 计算预览缩放比例
        preview_w, preview_h = self.display_pil_image.size
        original_w, original_h = self.original_pil_image.size
        scale = min(preview_w / original_w, preview_h / original_h)
        
        adjusted_params = self.adjust_watermark_params_for_preview(watermark_params, scale)
        wm_w, wm_h = self.estimate_watermark_size_for_preview(adjusted_params)
        new_x = max(0, min(new_x, preview_w - wm_w))
        new_y = max(0, min(new_y, preview_h - wm_h))
        
        # 保存预览坐标（用于拖拽过程）
        self.preview_watermark_position = (new_x, new_y)
        
        # 立即更新预览（使用快速路径）
        self.quick_update_position_with_preview_coords()
        
    def get_current_watermark_preview_position(self):
        """获取当前水印在预览图片中的位置"""
        if not self.display_pil_image:
            return (0, 0)
            
        # 计算预览缩放比例
        if not self.original_pil_image:
            scale = 1.0
        else:
            preview_w, preview_h = self.display_pil_image.size
            original_w, original_h = self.original_pil_image.size
            scale = min(preview_w / original_w, preview_h / original_h)
            
        # 获取水印尺寸（基于预览图片）
        watermark_params = self.get_current_watermark_params()
        adjusted_params = self.adjust_watermark_params_for_preview(watermark_params, scale)
        wm_w, wm_h = self.estimate_watermark_size_for_preview(adjusted_params)
        
        # 使用现有的位置计算逻辑（基于预览图片尺寸）
        img_w, img_h = self.display_pil_image.size
        return self.calculate_watermark_position(img_w, img_h, wm_w, wm_h, self.watermark_position)
        
    def estimate_watermark_size_for_preview(self, params):
        """估算水印在预览图片上的尺寸"""
        if params['type'] == 'text' and params['text']:
            # 使用调整后的字体参数
            try:
                font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{params['font'][0]}.ttf", params['font'][1])
            except IOError:
                font = ImageFont.load_default()
            
            try:
                text_bbox = font.getbbox(params['text'])
                text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
            except AttributeError:
                text_w, text_h = font.getsize(params['text'])
            
            # 如果有旋转，需要计算旋转后的尺寸
            if params['rotation'] != 0:
                txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
                draw = ImageDraw.Draw(txt_img)
                draw.text((0, 0), params['text'], font=font, fill=(0, 0, 0, 255))
                rotated_img = txt_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)
                return rotated_img.size
            
            return int(text_w), int(text_h)
            
        elif params['type'] == 'image' and params['image']:
            # 图片水印尺寸（使用调整后的缩放）
            wm_w, wm_h = params['image'].size
            scale = params['scale']
            scaled_w, scaled_h = int(wm_w * scale), int(wm_h * scale)
            
            # 如果有旋转，需要计算旋转后的尺寸
            if params['rotation'] != 0:
                scaled_img = params['image'].resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                rotated_img = scaled_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)
                return rotated_img.size
                
            return scaled_w, scaled_h
            
        return (50, 20)  # 默认尺寸
        
    def quick_update_position_with_preview_coords(self):
        """使用预览坐标快速更新水印位置"""
        if not self.display_pil_image or not hasattr(self, 'preview_watermark_position'):
            return
            
        # 复制基础图像
        image_with_watermark = self.display_pil_image.copy()
        
        # 获取调整后的水印参数
        watermark_params = self.get_current_watermark_params()
        
        # 计算预览缩放比例
        if self.original_pil_image:
            preview_w, preview_h = self.display_pil_image.size
            original_w, original_h = self.original_pil_image.size
            scale = min(preview_w / original_w, preview_h / original_h)
        else:
            scale = 1.0
        
        adjusted_params = self.adjust_watermark_params_for_preview(watermark_params, scale)
        
        # 临时覆盖位置为预览坐标
        x, y = self.preview_watermark_position
        
        if adjusted_params['type'] == "text" and adjusted_params['text']:
            # 直接应用文本水印到指定位置
            image_with_watermark = self.apply_text_watermark_at_position(image_with_watermark, adjusted_params, x, y)
        elif adjusted_params['type'] == "image" and adjusted_params['image']:
            # 直接应用图片水印到指定位置
            image_with_watermark = self.apply_image_watermark_at_position(image_with_watermark, adjusted_params, x, y)
        
        # 立即更新UI
        self.display_tk_image = ImageTk.PhotoImage(image_with_watermark)
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w/2, canvas_h/2, anchor="center", image=self.display_tk_image)

    def apply_text_watermark_at_position(self, image, params, x, y):
        """在指定位置应用文本水印"""
        font_name, font_size, color = params['font']
        alpha = int(255 * params['opacity'])
        fill_color = color + (alpha,)

        try:
            font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{font_name}.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        try:
            text_bbox = font.getbbox(params['text'])
            # 考虑bbox可能的负偏移
            left, top, right, bottom = text_bbox
            text_w = right - left
            text_h = bottom - top
        except AttributeError:
            text_w, text_h = font.getsize(params['text'])
            left, top = 0, 0

        txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)
        # 调整文本位置以补偿bbox偏移
        draw.text((-left, -top), params['text'], font=font, fill=fill_color)

        if params['rotation'] != 0:
            txt_img = txt_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)

        # 更新水印边界信息（用于拖拽检测）
        wm_w, wm_h = txt_img.size
        self.watermark_bounds = (x, y, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(txt_img, (int(x), int(y)))
        
        return Image.alpha_composite(image, watermark_layer)
    
    def apply_image_watermark_at_position(self, image, params, x, y):
        """在指定位置应用图片水印"""
        watermark_image = params['image']
        scale = params['scale']
        opacity = params['opacity']
        rotation = params['rotation']
        
        wm_w, wm_h = watermark_image.size
        new_wm_w = int(wm_w * scale)
        new_wm_h = int(wm_h * scale)
        
        if new_wm_w <= 0 or new_wm_h <= 0:
            return image

        scaled_wm = watermark_image.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)

        if rotation != 0:
            scaled_wm = scaled_wm.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

        if opacity < 1.0:
            alpha = scaled_wm.split()[3]
            alpha = alpha.point(lambda p: p * opacity)
            scaled_wm.putalpha(alpha)

        # 更新水印边界信息（用于拖拽检测）
        wm_w, wm_h = scaled_wm.size
        self.watermark_bounds = (x, y, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(scaled_wm, (int(x), int(y)), scaled_wm)
        
        return Image.alpha_composite(image, watermark_layer)

    def get_current_watermark_original_position(self):
        """获取当前水印在原始图片中的位置"""
        if not self.original_pil_image:
            return (0, 0)
            
        # 获取水印尺寸（基于原始图片）
        watermark_params = self.get_current_watermark_params()
        wm_w, wm_h = self.estimate_watermark_size_for_original(watermark_params)
        
        # 使用现有的位置计算逻辑（基于原始图片尺寸）
        img_w, img_h = self.original_pil_image.size
        return self.calculate_watermark_position(img_w, img_h, wm_w, wm_h, self.watermark_position)
        
    def estimate_watermark_size_for_original(self, params):
        """精确计算水印在原始图片上的尺寸，与实际渲染保持一致"""
        if params['type'] == 'text' and params['text']:
            # 使用与实际渲染相同的字体计算逻辑
            try:
                font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{params['font'][0]}.ttf", params['font'][1])
            except IOError:
                font = ImageFont.load_default()
            
            try:
                text_bbox = font.getbbox(params['text'])
                left, top, right, bottom = text_bbox
                text_w, text_h = right - left, bottom - top
            except AttributeError:
                text_w, text_h = font.getsize(params['text'])
                left, top = 0, 0
            
            # 如果有旋转，需要创建临时图像来计算旋转后的真实尺寸
            if params['rotation'] != 0:
                # 创建临时文本图像
                txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
                draw = ImageDraw.Draw(txt_img)
                # 调整文本位置以补偿bbox偏移
                draw.text((-left, -top), params['text'], font=font, fill=(0, 0, 0, 255))
                
                # 旋转图像并获取真实尺寸
                rotated_img = txt_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)
                return rotated_img.size
            
            return int(text_w), int(text_h)
            
        elif params['type'] == 'image' and params['image']:
            # 图片水印尺寸计算
            wm_w, wm_h = params['image'].size
            scale = params['scale']
            scaled_w, scaled_h = int(wm_w * scale), int(wm_h * scale)
            
            # 如果有旋转，需要计算旋转后的真实尺寸
            if params['rotation'] != 0:
                # 创建临时缩放图像
                scaled_img = params['image'].resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
                
                # 旋转图像并获取真实尺寸
                rotated_img = scaled_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)
                return rotated_img.size
                
            return scaled_w, scaled_h
            
        return (50, 20)  # 默认尺寸

    def get_current_watermark_image_position(self):
        """获取当前水印在图片中的位置"""
        if not self.display_pil_image:
            return (0, 0)
            
        # 获取水印尺寸
        watermark_params = self.get_current_watermark_params()
        wm_w, wm_h = self.estimate_watermark_size(watermark_params)
        
        # 使用现有的位置计算逻辑
        img_w, img_h = self.display_pil_image.size
        return self.calculate_watermark_position(img_w, img_h, wm_w, wm_h, self.watermark_position)
        
    def estimate_watermark_size(self, params):
        """估算水印尺寸（用于拖拽检测），基于预览图片尺寸"""
        if not self.display_pil_image or not self.original_pil_image:
            return (50, 20)
            
        # 获取原始尺寸
        original_w, original_h = self.estimate_watermark_size_for_original(params)
        
        # 计算预览缩放比例
        preview_w, preview_h = self.display_pil_image.size
        orig_img_w, orig_img_h = self.original_pil_image.size
        scale_x = preview_w / orig_img_w
        scale_y = preview_h / orig_img_h
        
        # 将原始水印尺寸缩放到预览尺寸
        preview_wm_w = int(original_w * scale_x)
        preview_wm_h = int(original_h * scale_y)
        
        return preview_wm_w, preview_wm_h

    def select_image(self, index):
        if 0 <= index < len(self.image_paths):
            self.current_image_index = index
            path = self.image_paths[self.current_image_index]
            try:
                self.original_pil_image = Image.open(path).convert("RGBA")
                # 切换图片时清除自定义位置
                self.custom_watermark_position = None
                self.watermark_bounds = None
                # 清除临时预览位置
                if hasattr(self, 'preview_watermark_position'):
                    delattr(self, 'preview_watermark_position')
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
        """优化的异步预览更新，支持缓存和优先级"""
        if not self.original_pil_image:
            return

        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1: 
            return

        # 递增处理ID，用于取消过期的处理
        self.current_processing_id += 1
        processing_id = self.current_processing_id

        # 检查是否只是位置变化（快速路径）
        watermark_params = self.get_current_watermark_params()
        position_only_change = self.is_position_only_change(watermark_params)
        
        if position_only_change and self.base_watermark_image is not None:
            # 快速路径：只有位置变化，直接重新定位水印
            self.quick_update_position()
            return

        # 准备图像数据  
        image_data = (self.original_pil_image, (canvas_w, canvas_h), rescale)
        
        # 异步生成预览（带缓存）
        self.async_generate_preview_cached(image_data, watermark_params, processing_id, 
                                          lambda result: self.on_preview_ready_cached(result, processing_id))

    def get_current_watermark_params(self):
        """获取当前水印参数"""
        watermark_type = self.watermark_type.get()
        text_content = self.text_entry.get() if watermark_type == "text" else ""
        font_params = (self.watermark_font, self.watermark_font_size, self.watermark_color)
        image_watermark = self.image_watermark_pil if watermark_type == "image" else None
        opacity = self.opacity_slider.get() if watermark_type == "text" else self.image_opacity_slider.get()
        scale = self.image_scale_slider.get() if watermark_type == "image" else 1.0
        
        return {
            'type': watermark_type,
            'text': text_content,
            'font': font_params,
            'image': image_watermark,
            'position': self.watermark_position,
            'rotation': self.watermark_rotation,
            'opacity': opacity,
            'scale': scale
        }

    def is_position_only_change(self, current_params):
        """检查是否只有位置参数发生了变化"""
        if self.last_watermark_params is None:
            return False
            
        last = self.last_watermark_params
        current = current_params
        
        # 检查除位置外的所有参数是否相同
        position_independent_keys = ['type', 'text', 'font', 'image', 'rotation', 'opacity', 'scale']
        for key in position_independent_keys:
            if last.get(key) != current.get(key):
                return False
        
        # 只有位置不同
        return last.get('position') != current.get('position')

    def quick_update_position(self):
        """快速更新水印位置，无需重新生成水印"""
        if not self.base_watermark_image or not self.display_pil_image:
            return
            
        # 复制基础图像
        image_with_watermark = self.display_pil_image.copy()
        
        # 获取水印参数并调整为预览尺寸
        watermark_params = self.get_current_watermark_params()
        
        # 计算预览缩放比例
        if self.original_pil_image:
            preview_w, preview_h = self.display_pil_image.size
            original_w, original_h = self.original_pil_image.size
            scale = min(preview_w / original_w, preview_h / original_h)
        else:
            scale = 1.0
            
        adjusted_params = self.adjust_watermark_params_for_preview(watermark_params, scale)
        
        if adjusted_params['type'] == "text" and adjusted_params['text']:
            # 快速文本水印重定位
            image_with_watermark = self.apply_cached_text_watermark(image_with_watermark, adjusted_params)
        elif adjusted_params['type'] == "image" and adjusted_params['image']:
            # 快速图片水印重定位  
            image_with_watermark = self.apply_cached_image_watermark(image_with_watermark, adjusted_params)
        
        # 立即更新UI
        self.display_tk_image = ImageTk.PhotoImage(image_with_watermark)
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w/2, canvas_h/2, anchor="center", image=self.display_tk_image)

    def apply_cached_text_watermark(self, image, params):
        """应用缓存的文本水印到新位置"""
        # 为预览缩放调整生成唯一的缓存key
        font_name, font_size, color = params['font']
        cache_key = f"text_{params['text']}_{font_name}_{font_size}_{params['rotation']}_{params['opacity']}"
        
        if cache_key not in self.watermark_cache:
            # 生成水印文本图像并缓存
            alpha = int(255 * params['opacity'])
            fill_color = color + (alpha,)

            try:
                font = ImageFont.truetype(f"/System/Library/Fonts/Supplemental/{font_name}.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()

            try:
                text_bbox = font.getbbox(params['text'])
                # 考虑bbox可能的负偏移
                left, top, right, bottom = text_bbox
                text_w = right - left
                text_h = bottom - top
            except AttributeError:
                text_w, text_h = font.getsize(params['text'])
                left, top = 0, 0

            txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_img)
            # 调整文本位置以补偿bbox偏移
            draw.text((-left, -top), params['text'], font=font, fill=fill_color)

            if params['rotation'] != 0:
                txt_img = txt_img.rotate(params['rotation'], expand=True, resample=Image.Resampling.BICUBIC)

            self.watermark_cache[cache_key] = txt_img
        
        # 应用到新位置
        txt_img = self.watermark_cache[cache_key]
        wm_w, wm_h = txt_img.size
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, params['position'])
        
        # 更新水印边界信息（用于拖拽检测）
        self.watermark_bounds = (x, y, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(txt_img, (x, y))
        
        return Image.alpha_composite(image, watermark_layer)

    def apply_cached_image_watermark(self, image, params):
        """应用缓存的图片水印到新位置"""
        watermark_image = params['image']
        scale = params['scale']
        opacity = params['opacity']
        rotation = params['rotation']
        
        # 缓存键包含所有影响水印外观的参数
        cache_key = f"image_{id(watermark_image)}_{scale}_{opacity}_{rotation}"
        
        if cache_key not in self.watermark_cache:
            # 处理图片水印并缓存
            wm_w, wm_h = watermark_image.size
            new_wm_w = int(wm_w * scale)
            new_wm_h = int(wm_h * scale)
            
            if new_wm_w > 0 and new_wm_h > 0:
                scaled_wm = watermark_image.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)

                if rotation != 0:
                    scaled_wm = scaled_wm.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

                if opacity < 1.0:
                    alpha = scaled_wm.split()[3]
                    alpha = alpha.point(lambda p: p * opacity)
                    scaled_wm.putalpha(alpha)

                self.watermark_cache[cache_key] = scaled_wm
            else:
                return image
        
        # 应用到新位置
        scaled_wm = self.watermark_cache[cache_key]
        wm_w, wm_h = scaled_wm.size
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, params['position'])
        
        # 更新水印边界信息（用于拖拽检测）
        self.watermark_bounds = (x, y, wm_w, wm_h)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(scaled_wm, (x, y), scaled_wm)
        
        return Image.alpha_composite(image, watermark_layer)

    def async_generate_preview_cached(self, image_data, watermark_params, processing_id, callback):
        """带缓存和优先级的异步预览生成"""
        def worker():
            try:
                # 检查任务是否已过期
                if processing_id != self.current_processing_id:
                    return  # 任务已被新任务取代
                
                # 解包参数
                original_image, canvas_size, rescale = image_data
                
                # 计算显示尺寸和缩放比例
                preview_scale = 1.0
                if rescale or not hasattr(self, 'display_pil_image') or self.display_pil_image is None:
                    canvas_w, canvas_h = canvas_size
                    img_w, img_h = original_image.size
                    ratio = min(canvas_w / img_w, canvas_h / img_h)
                    new_w = int(img_w * ratio)
                    new_h = int(img_h * ratio)
                    display_image = original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    preview_scale = ratio  # 记录预览缩放比例
                else:
                    display_image = self.display_pil_image
                    # 计算当前预览的缩放比例
                    if self.original_pil_image:
                        orig_w, orig_h = self.original_pil_image.size
                        disp_w, disp_h = display_image.size
                        preview_scale = min(disp_w / orig_w, disp_h / orig_h)

                # 再次检查任务是否过期
                if processing_id != self.current_processing_id:
                    return
                
                # 复制用于水印处理
                image_to_draw = display_image.copy()
                
                # 创建调整后的水印参数（针对预览缩放）
                adjusted_params = self.adjust_watermark_params_for_preview(watermark_params, preview_scale)
                
                # 添加水印（使用缓存优化）
                if adjusted_params['type'] == "text" and adjusted_params['text']:
                    image_with_watermark = self.apply_cached_text_watermark(image_to_draw, adjusted_params)
                elif adjusted_params['type'] == "image" and adjusted_params['image']:
                    image_with_watermark = self.apply_cached_image_watermark(image_to_draw, adjusted_params)
                else:
                    image_with_watermark = image_to_draw
                
                # 最后检查任务是否过期
                if processing_id != self.current_processing_id:
                    return
                
                # 存储基础水印图像用于快速位置更新
                self.base_watermark_image = image_with_watermark
                self.last_watermark_params = watermark_params.copy()
                
                # 将PIL图像结果放入队列（不在这里转换为Tkinter格式）
                self.preview_queue.put((callback, (image_with_watermark, display_image)))
                
            except Exception as e:
                print(f"Cached preview generation error: {e}")
                self.preview_queue.put((callback, None))
        
        # 启动后台线程
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def on_preview_ready_cached(self, result, processing_id):
        """缓存预览生成完成的回调"""
        # 检查结果是否仍然有效
        if processing_id != self.current_processing_id:
            return  # 忽略过期的结果
            
        if result is None:
            return
            
        image_with_watermark, display_image = result
        
        # 在主线程中转换为Tkinter格式
        try:
            tk_image = ImageTk.PhotoImage(image_with_watermark)
        except Exception as e:
            print(f"Error converting to Tkinter image: {e}")
            return
        
        # 更新成员变量
        self.display_pil_image = display_image
        self.display_tk_image = tk_image
        
        # 更新Canvas
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w/2, canvas_h/2, anchor="center", image=self.display_tk_image)

    def on_preview_ready(self, result):
        """预览生成完成的回调"""
        if result is None:
            return
            
        image_with_watermark, display_image = result
        
        # 在主线程中转换为Tkinter格式
        try:
            tk_image = ImageTk.PhotoImage(image_with_watermark)
        except Exception as e:
            print(f"Error converting to Tkinter image: {e}")
            return
        
        # 更新成员变量
        self.display_pil_image = display_image
        self.display_tk_image = tk_image
        
        # 更新Canvas
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w/2, canvas_h/2, anchor="center", image=self.display_tk_image)

    def select_image_watermark(self):
        file_types = [("Image files", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="选择水印图片", filetypes=file_types)
        if path:
            try:
                self.image_watermark_pil = Image.open(path).convert("RGBA")
                self.image_watermark_pil.filename = path # Store path for saving
                self.debounced_update_preview()
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
            # 考虑bbox可能的负偏移
            left, top, right, bottom = text_bbox
            text_w, text_h = right - left, bottom - top
        except AttributeError:
            text_w, text_h = font.getsize(watermark_text)
            left, top = 0, 0

        txt_img = Image.new('RGBA', (text_w, text_h), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_img)
        # 调整文本位置以补偿bbox偏移
        draw.text((-left, -top), watermark_text, font=font, fill=fill_color)

        # Rotate the text image
        if self.watermark_rotation != 0:
            txt_img = txt_img.rotate(self.watermark_rotation, expand=True, resample=Image.Resampling.BICUBIC)

        # Get position and paste
        wm_w, wm_h = txt_img.size
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, self.watermark_position)
        
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
        x, y = self.calculate_watermark_position(image.width, image.height, wm_w, wm_h, self.watermark_position)
        
        watermark_layer = Image.new('RGBA', image.size, (255, 255, 255, 0))
        watermark_layer.paste(scaled_wm, (x, y), scaled_wm)

        return Image.alpha_composite(image, watermark_layer)

    def set_font(self, font_name):
        self.watermark_font = font_name
        self.debounced_update_preview()

    def set_font_size(self, event=None):
        try:
            size = int(self.font_size_entry.get())
            if size > 0:
                self.watermark_font_size = size
                self.clear_watermark_cache()  # 清除缓存，因为字体大小改变了
                self.debounced_update_preview()
        except ValueError:
            pass # Ignore non-integer input

    def set_position(self, position_code):
        """优化的位置设置，使用快速更新路径"""
        print("Setting position to:", position_code)
        old_position = self.watermark_position
        self.watermark_position = position_code
        
        # 清除自定义位置，使用预设位置
        self.custom_watermark_position = None
        
        # 如果有缓存的水印，使用快速路径
        if (self.base_watermark_image is not None and 
            self.last_watermark_params is not None and 
            self.display_pil_image is not None):
            self.quick_update_position()
        else:
            # 降级到正常更新
            self.update_preview()

    def set_position_with_refresh(self, position_code):
        """简化的位置设置"""
        self.set_position(position_code)
        self.update_preview()

    def set_rotation(self, angle):
        self.watermark_rotation = int(angle)
        self.debounced_update_preview()

    def debounced_update_preview(self, event=None):
        """Cancels the previous update job and schedules a new one."""
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
        self._debounce_job = self.after(100, self.update_preview) # 恢复合理的延迟时间

    def update_preview(self, event=None):
        """The actual preview update function."""
        self.display_current_image(rescale=False) # 仅更新水印，不重新缩放

    def on_watermark_type_changed(self):
        """Handle watermark type change and update UI visibility."""
        watermark_type = self.watermark_type.get()
        
        if watermark_type == "text":
            # 显示文本水印相关控件，隐藏图片水印控件
            self.text_watermark_frame.pack(pady=10, padx=10, fill="x")
            self.image_watermark_frame.pack_forget()
        else:  # watermark_type == "image"
            # 显示图片水印相关控件，隐藏文本水印控件
            self.image_watermark_frame.pack(pady=10, padx=10, fill="x")
            self.text_watermark_frame.pack_forget()
        
        # 更新预览
        self.debounced_update_preview()

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

        # 使用预设的输出路径，如果没有设置则提示用户选择
        output_dir = self.output_directory.get()
        
        if not output_dir:
            # 提示用户先设置输出路径
            result = messagebox.askyesno("设置输出路径", 
                                       "尚未设置输出路径。是否现在选择输出文件夹？")
            if result:
                self.choose_output_directory()
                output_dir = self.output_directory.get()
            
            if not output_dir:
                return
        
        # 验证输出目录是否存在
        if not os.path.exists(output_dir):
            messagebox.showerror("错误", f"输出路径不存在：{output_dir}\n请重新选择输出文件夹。")
            self.choose_output_directory()
            output_dir = self.output_directory.get()
            if not output_dir:
                return

        # Prevent overwriting - 防止导出到原始图片所在的文件夹
        input_dirs = {os.path.dirname(p) for p in self.image_paths}
        if output_dir in input_dirs:
            messagebox.showerror("错误", "不能导出到原始图片所在的文件夹，请选择其他文件夹。")
            # 提供重新选择的机会
            self.choose_output_directory()
            output_dir = self.output_directory.get()
            if not output_dir or output_dir in input_dirs:
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
                # 定期刷新UI
                if i % 5 == 0:  # 每5张图片刷新一次UI
                    progress_win.update_idletasks()

            except Exception as e:
                print(f"Error processing {path}: {e}")

        progress_win.destroy()
        messagebox.showinfo("完成", f"成功处理并导出了 {total_images} 张图片。")

    def quit_app(self):
        """清理资源并关闭应用"""
        self.is_closing = True
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
            "output_directory": self.output_directory.get(),  # 添加输出路径
            "jpeg_quality": self.jpeg_quality.get(),
            # 添加模板相关设置
            "last_template_name": self.current_template_name,
            "auto_load_last": self.auto_load_last.get(),
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
        # 加载输出路径设置
        self.output_directory.set(settings.get("output_directory", ""))
        self.update_output_path_display()  # 更新路径显示
        self.jpeg_quality.set(settings.get("jpeg_quality", 95))
        
        # 加载模板相关设置
        if hasattr(self, 'auto_load_last'):
            self.auto_load_last.set(settings.get("auto_load_last", True))

        self.on_watermark_type_changed() # Update UI visibility based on loaded type

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

    # ==================== 模板管理系统 ====================
    
    def init_template_system(self):
        """初始化模板管理系统"""
        # 创建模板文件夹
        if not os.path.exists(self.templates_dir):
            os.makedirs(self.templates_dir)
        
        # 刷新模板列表
        self.refresh_template_list()
        
    def refresh_template_list(self):
        """刷新模板下拉菜单"""
        template_files = []
        if os.path.exists(self.templates_dir):
            for file in os.listdir(self.templates_dir):
                if file.endswith(self.template_extension):
                    template_name = file[:-len(self.template_extension)]
                    template_files.append(template_name)
        
        # 排序模板名称
        template_files.sort()
        
        # 更新下拉菜单
        if template_files:
            self.template_combobox.configure(values=["<无模板>"] + template_files)
        else:
            self.template_combobox.configure(values=["<无模板>"])
            
        # 如果当前选择的模板不存在了，重置为无模板
        current_selection = self.template_combobox.get()
        if current_selection not in ["<无模板>"] + template_files:
            self.template_combobox.set("<无模板>")
            self.current_template_name = None
    
    def get_template_path(self, template_name):
        """获取模板文件的完整路径"""
        return os.path.join(self.templates_dir, f"{template_name}{self.template_extension}")
    
    def save_new_template(self):
        """保存新模板"""
        # 获取模板名称
        template_name = ctk.CTkInputDialog(
            text="请输入模板名称:", 
            title="保存水印模板"
        ).get_input()
        
        if not template_name:
            return
            
        # 验证模板名称
        if not self.validate_template_name(template_name):
            messagebox.showerror("错误", "模板名称不能包含特殊字符或为空。")
            return
            
        template_path = self.get_template_path(template_name)
        
        # 检查是否覆盖现有模板
        if os.path.exists(template_path):
            result = messagebox.askyesno("确认覆盖", f"模板 '{template_name}' 已存在。是否覆盖？")
            if not result:
                return
        
        # 保存模板
        try:
            settings = self.get_settings_as_dict()
            # 添加模板元数据
            settings["template_metadata"] = {
                "name": template_name,
                "created_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version": "1.0"
            }
            
            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
                
            self.current_template_name = template_name
            self.refresh_template_list()
            self.template_combobox.set(template_name)
            
            messagebox.showinfo("成功", f"模板 '{template_name}' 已保存。")
            
        except Exception as e:
            messagebox.showerror("错误", f"保存模板失败: {e}")
    
    def load_template_by_name(self, template_name):
        """根据名称加载模板"""
        if template_name == "<无模板>":
            self.current_template_name = None
            return
            
        template_path = self.get_template_path(template_name)
        
        if not os.path.exists(template_path):
            messagebox.showerror("错误", f"模板文件不存在: {template_path}")
            self.refresh_template_list()
            return
            
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                
            self.apply_settings_from_dict(settings)
            self.current_template_name = template_name
            
            # 清除自定义位置，使用模板中的预设位置
            self.custom_watermark_position = None
            self.watermark_bounds = None
            
            # 更新预览
            self.debounced_update_preview()
            
            messagebox.showinfo("成功", f"已加载模板 '{template_name}'。")
            
        except Exception as e:
            messagebox.showerror("错误", f"加载模板失败: {e}")
            self.current_template_name = None
            self.template_combobox.set("<无模板>")
    
    def rename_template(self):
        """重命名当前选中的模板"""
        current_template = self.template_combobox.get()
        
        if current_template == "<无模板>":
            messagebox.showwarning("提示", "请先选择要重命名的模板。")
            return
            
        new_name = ctk.CTkInputDialog(
            text=f"请输入新的模板名称:", 
            title="重命名模板"
        ).get_input()
        
        if not new_name:
            return
            
        if not self.validate_template_name(new_name):
            messagebox.showerror("错误", "模板名称不能包含特殊字符或为空。")
            return
            
        if new_name == current_template:
            return  # 名称没有变化
            
        old_path = self.get_template_path(current_template)
        new_path = self.get_template_path(new_name)
        
        # 检查新名称是否已存在
        if os.path.exists(new_path):
            messagebox.showerror("错误", f"模板名称 '{new_name}' 已存在。")
            return
            
        try:
            # 重命名文件
            os.rename(old_path, new_path)
            
            # 更新模板内部的元数据
            with open(new_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            
            if "template_metadata" in settings:
                settings["template_metadata"]["name"] = new_name
                settings["template_metadata"]["modified_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            
            self.current_template_name = new_name
            self.refresh_template_list()
            self.template_combobox.set(new_name)
            
            messagebox.showinfo("成功", f"模板已重命名为 '{new_name}'。")
            
        except Exception as e:
            messagebox.showerror("错误", f"重命名模板失败: {e}")
    
    def delete_template(self):
        """删除当前选中的模板"""
        current_template = self.template_combobox.get()
        
        if current_template == "<无模板>":
            messagebox.showwarning("提示", "请先选择要删除的模板。")
            return
            
        result = messagebox.askyesno("确认删除", f"确定要删除模板 '{current_template}' 吗？此操作不可撤销。")
        
        if not result:
            return
            
        template_path = self.get_template_path(current_template)
        
        try:
            os.remove(template_path)
            
            self.current_template_name = None
            self.refresh_template_list()
            self.template_combobox.set("<无模板>")
            
            messagebox.showinfo("成功", f"模板 '{current_template}' 已删除。")
            
        except Exception as e:
            messagebox.showerror("错误", f"删除模板失败: {e}")
    
    def validate_template_name(self, name):
        """验证模板名称是否有效"""
        if not name or not name.strip():
            return False
            
        # 检查是否包含不允许的字符
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for char in invalid_chars:
            if char in name:
                return False
                
        return True
    
    def load_last_settings_or_default_template(self):
        """启动时自动加载上次设置或默认模板"""
        if not self.auto_load_last.get():
            return
            
        # 首先尝试加载上次的设置
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, "r") as f:
                    settings = json.load(f)
                    
                # 检查是否有上次使用的模板
                last_template = settings.get("last_template_name")
                if last_template and last_template != "<无模板>":
                    template_path = self.get_template_path(last_template)
                    if os.path.exists(template_path):
                        self.template_combobox.set(last_template)
                        self.load_template_by_name(last_template)
                        return
                        
                # 如果没有有效的模板，加载基本设置
                self.apply_settings_from_dict(settings)
                
        except Exception as e:
            print(f"Failed to load last settings: {e}")

if __name__ == "__main__":
    app = WatermarkApp()
    app.mainloop()
