import json
import os
import tkinter as tk
import time
from tkinter import filedialog, messagebox
import pygame
import threading

class AnchorNode:
    def __init__(self, anchor,isTail=False):
        self.isTail = isTail  # 新增属性，标记尾锚点
        self.anchor = anchor
        self.next = None
        self.prev = None

class AnchorLinkedList:
    def __init__(self):
        self.head = None

    def insert_anchor(self, new_anchor,isTail=False):
        new_node = AnchorNode(new_anchor)
        new_node.isTail=isTail
        if not self.head or new_anchor.time_position < self.head.anchor.time_position:
            new_node.next = self.head
            if self.head:
                self.head.prev = new_node
            self.head = new_node
        else:
            current = self.head
            while current.next and current.next.anchor.time_position < new_anchor.time_position:
                current = current.next
            new_node.next = current.next
            if current.next:
                current.next.prev = new_node
            current.next = new_node
            new_node.prev = current 

    def delete_nearest_anchor(self, current_time):
        if not self.head:
            return None
        closest_node = self.head
        min_diff = abs(current_time - closest_node.anchor.time_position)
        current = self.head.next

        while current:
            diff = abs(current_time - current.anchor.time_position)
            if diff < min_diff:
                closest_node = current
                min_diff = diff
            current = current.next

        # 从链表中删除最近的锚点(尾节点不删除)
        if not closest_node.isTail:
            if closest_node.prev:
                closest_node.prev.next = closest_node.next
            else:
                self.head = closest_node.next
            if closest_node.next:
                closest_node.next.prev = closest_node.prev

        return closest_node.anchor

    def get_next_anchor(self, current_time):
        current = self.head
        while current and current.anchor.time_position <= current_time:
            current = current.next
        return current.anchor if current else None

    def get_prev_anchor(self, current_time):
        current = self.head
        while current and current.anchor.time_position < current_time:
            current = current.next
        return current.prev.anchor if current and current.prev else None

    # 设置成可迭代对象，以使用json
    def __iter__(self):
        current = self.head
        while current:
            yield current.anchor
            current = current.next

class Anchor:
    def __init__(self, time_position):
        self.time_position = time_position

    def format_time(self):
        hours = int(self.time_position // 3600)
        minutes = int((self.time_position % 3600) // 60)
        secs = int(self.time_position % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def __str__(self):
        return f"锚点: {self.format_time()}"

class JSONManager:
    def __init__(self, json_file="mp3播放器锚点配置文件/anchor.json"):
        # 确保config文件夹存在
        config_dir = os.path.dirname(json_file)  # 获取config文件夹路径
        os.makedirs(config_dir, exist_ok=True)   # 创建文件夹（如果不存在的话）

        self.json_file = json_file
        self.data = self.load_json()

    def load_json(self):
        if not os.path.exists(self.json_file):
            with open(self.json_file, 'w') as f:
                json.dump({}, f)
        with open(self.json_file, 'r') as f:
            return json.load(f)

    def save_json(self):
        with open(self.json_file, 'w') as f:
            json.dump(self.data, f, indent=4)

    def save_anchors_for_file(self, file_name, anchor_times):
        self.data[file_name] = anchor_times
        self.save_json()

    def load_anchors_for_file(self, file_name):
        if file_name in self.data:
            return [Anchor(time_pos) for time_pos in self.data[file_name]]
        return []

    def delete_specific_anchor(self, file_name, anchor_time):
        """ 删除指定 file_name 对应的特定锚点数据 """
        if file_name in self.data:
            # 检查锚点时间是否在列表中
            if anchor_time in self.data[file_name]:
                self.data[file_name].remove(anchor_time)  # 从锚点列表中删除特定时间
                self.save_json()  # 保存更新后的数据
                print(f"已删除文件 '{file_name}' 的锚点时间 {anchor_time}。")
            else:
                print(f"锚点时间 {anchor_time} 不存在于文件 '{file_name}' 中。")
        else:
            print(f"文件 '{file_name}' 不存在，无法删除锚点。")

class MP3Player:
    def __init__(self, root):
        self.root = root
        self.root.title("MP3 播放器(按L加载文件)")
        self.root.geometry("800x400")
        pygame.mixer.init()

        self.playing = False
        self.paused = False
        self.file_path = None
        self.total_length = 0
        self.current_pos = 0
        self.lock = threading.Lock()
        self.last_update_time = time.time()
        self.dragging = False
        self.anchors = AnchorLinkedList()
        self.json_manager = JSONManager()
        self.current_file_name = None
        self.pause_time=None   # 记录暂停时的时间

        # 播放控制区
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)

        self.rewind_button = tk.Button(control_frame, text="<< 5s\n快捷键：方向👈", command=self.rewind)
        self.rewind_button.pack(side=tk.LEFT, padx=10)

        self.play_button = tk.Button(control_frame, text="播放\n快捷键：SPACE", command=self.play_pause)
        self.play_button.pack(side=tk.LEFT, padx=10)

        self.forward_button = tk.Button(control_frame, text=">> 5s\n快捷键：方向👉", command=self.forward)
        self.forward_button.pack(side=tk.LEFT, padx=10)


        self.progress_canvas = tk.Canvas(self.root, width=500, height=30, bg="lightgray")
        self.progress_canvas.pack(padx=20, pady=20)
        self.progress_canvas.bind("<ButtonPress-1>", self.start_drag)
        self.progress_canvas.bind("<ButtonRelease-1>", self.stop_drag)

        self.time_label = tk.Label(self.root, text="00:00:00")
        self.time_label.pack()

        # 锚点控制区
        anchor_frame = tk.Frame(self.root)
        anchor_frame.pack(pady=10)

        self.prev_anchor_button = tk.Button(anchor_frame, text="上一锚点\n快捷键：方向键⬆️", command=self.prev_anchor)
        self.prev_anchor_button.pack(side=tk.LEFT, padx=10)

        self.next_anchor_button = tk.Button(anchor_frame, text="下一锚点\n快捷键：方向键⬇️", command=self.next_anchor)
        self.next_anchor_button.pack(side=tk.LEFT, padx=10)

        self.anchor_button = tk.Button(anchor_frame, text="添加锚点\n快捷键：M", command=self.add_anchor)
        self.anchor_button.pack(side=tk.LEFT, padx=10)

        self.delete_anchor_button = tk.Button(anchor_frame, text="删除锚点\n快捷键：X", command=self.delete_nearest_anchor)
        self.delete_anchor_button.pack(side=tk.LEFT, padx=10)
        # 锚点列表
        self.anchor_list = tk.Listbox(self.root, width=100, height=10)
        self.anchor_list.pack(padx=10, pady=10)



        # 绑定快捷键
        self.root.bind("<space>", lambda event: self.play_pause())
        self.root.bind("<Down>", lambda event: self.next_anchor())
        self.root.bind("<Up>", lambda event: self.prev_anchor())
        self.root.bind("<l>", lambda event: self.load_file())
        self.root.bind("<m>", lambda event: self.add_anchor())
        self.root.bind("<x>", lambda event: self.delete_nearest_anchor())
        self.root.bind("<Right>", lambda event: self.forward())
        self.root.bind("<Left>", lambda event: self.rewind())


    def load_file(self):
        self.file_path = filedialog.askopenfilename(filetypes=[("MP3 files", "*.mp3")])
        if self.file_path:
            pygame.mixer.music.load(self.file_path)
            self.playing = False
            self.current_pos = 0
            self.last_update_time = time.time()
            self.total_length = pygame.mixer.Sound(self.file_path).get_length()

            self.anchor_list.delete(0, tk.END)
            self.anchors = AnchorLinkedList()

            file_name = os.path.basename(self.file_path)
            self.current_file_name = file_name

            saved_anchors = self.json_manager.load_anchors_for_file(file_name)
            for anchor in saved_anchors:
                self.anchors.insert_anchor(anchor)
                self.anchor_list.insert(tk.END, str(anchor))

            self.update_progress_bar()
            self.time_label.config(text=Anchor(self.current_pos).format_time())
            # 插入尾节点，防止BUG
            new_anchor = Anchor(self.total_length)
            self.anchors.insert_anchor(new_anchor,isTail=True)
#--------------------------------------------------------



    def play_pause(self):
        if self.file_path:
            if not self.playing:
                pygame.mixer.music.play(start=self.current_pos)
                self.playing = True
                self.paused = False
                self.play_button.config(text="暂停（按L加载新文件）")
                self.update_progress()
            elif self.paused:
                pygame.mixer.music.unpause()
                self.paused = False
                # 下面返回当前暂停时间
                self.current_pos = self.pause_time
                pygame.mixer.music.set_pos(self.current_pos)
                self.last_update_time = time.time()
                self.play_button.config(text="暂停（按L加载新文件）")
            else:
                self.pause_time=self.current_pos    # 记录当前暂停时的时间
                pygame.mixer.music.pause()
                self.paused = True
                self.play_button.config(text="播放\n快捷键：SPACE")

    def add_anchor(self):
        anchor_time = self.current_pos
        new_anchor = Anchor(anchor_time)

        # 确保锚点之间间隔不小于1分钟
        anchor_times = [node.time_position for node in self.anchors]

        self.anchors.insert_anchor(new_anchor)
        self.anchor_list.insert(tk.END, str(new_anchor))
        self.json_manager.save_anchors_for_file(self.current_file_name, anchor_times + [anchor_time])


    # def delete_nearest_anchor(self):
    #     deleted_anchor = self.anchors.delete_nearest_anchor(self.current_pos)
    #     if deleted_anchor:
    #         for i in range(self.anchor_list.size()):
    #             if self.anchor_list.get(i) == str(deleted_anchor):
    #                 self.anchor_list.delete(i)
    #                 break
    #         self.update_progress_bar()
    #     else:
    #         messagebox.showwarning("警告", "没有锚点可删除！")

    def delete_nearest_anchor(self):
        deleted_anchor = self.anchors.delete_nearest_anchor(self.current_pos)
        if deleted_anchor:
            # 从锚点列表中找到并删除该锚点
            for i in range(self.anchor_list.size()):
                if self.anchor_list.get(i) == str(deleted_anchor):
                    self.anchor_list.delete(i)
                    break
                
            # 从 JSON 中删除对应的锚点时间
            if self.current_file_name is not None:
                anchor_time = deleted_anchor.time_position  # 获取要删除的锚点时间
                self.json_manager.delete_specific_anchor(self.current_file_name, anchor_time)
    
            self.update_progress_bar()
        else:
            messagebox.showwarning("警告", "没有锚点可删除！")
    


    def update_progress(self):
        self.root.after(500, self.update_progress)
        if self.playing and not self.paused and not self.dragging:
            with self.lock:
                current_time = time.time()
                elapsed_time = current_time - self.last_update_time
                self.current_pos += elapsed_time
                self.current_pos = min(self.current_pos, self.total_length)
                self.last_update_time = current_time
                self.update_progress_bar()
                self.time_label.config(text=Anchor(self.current_pos).format_time())

    # 快进
    def forward(self):
        if self.playing:
            with self.lock:
                self.current_pos = min(self.total_length, self.current_pos + 5)
                pygame.mixer.music.set_pos(self.current_pos)
                #self.progress.set(self.current_pos)
                self.last_update_time = time.time()

    # 回退
    def rewind(self):
        if self.playing:
            with self.lock:
                self.current_pos = max(0, self.current_pos - 5)
                pygame.mixer.music.set_pos(self.current_pos)
                #self.progress.set(self.current_pos)
                self.last_update_time = time.time()
    # 拖拽函数
    def start_drag(self, event):
        self.dragging = True
    # 拖拽函数
    def stop_drag(self, event):
        self.dragging = False
        self.current_pos = event.x / self.progress_canvas.winfo_width() * self.total_length
        pygame.mixer.music.set_pos(self.current_pos)
        self.last_update_time = time.time()

    def next_anchor(self):
        next_anchor = self.anchors.get_next_anchor(self.current_pos)
        if next_anchor:
            self.jump_to_anchor(next_anchor)

    def prev_anchor(self):
        prev_anchor = self.anchors.get_prev_anchor(self.current_pos - 5)
        if prev_anchor:
            self.jump_to_anchor(prev_anchor)

    def jump_to_anchor(self, anchor):
        with self.lock:
            self.current_pos = anchor.time_position
            pygame.mixer.music.set_pos(self.current_pos)
            self.last_update_time = time.time()

    def update_progress_bar(self):
        self.progress_canvas.delete("all")
        progress_position = (self.current_pos / self.total_length) * self.progress_canvas.winfo_width()
        self.progress_canvas.create_rectangle(0, 0, progress_position, 30, fill="blue")

        current = self.anchors.head
        while current:
            anchor_position = (current.anchor.time_position / self.total_length) * self.progress_canvas.winfo_width()
            self.progress_canvas.create_line(anchor_position, 0, anchor_position, 30, fill="red", width=2)
            current = current.next

root = tk.Tk()
app = MP3Player(root)
root.mainloop()