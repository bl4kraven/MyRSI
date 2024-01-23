#!/usr/bin/env python
import sys
import wx
from wx import adv
import struct, socket
from threading import Thread
from wx.lib.pubsub import pub

MODE_NONE = 0
MODE_CLIENT = 1
MODE_SERVER = 2

def singleton(class_):
    instances = {}
    def getinstance(*args, **kwargs):
        if class_ not in instances:
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]
    return getinstance

class SettingDialog(wx.Dialog):

    def __init__(self, *args, **kvs):
        wx.Dialog.__init__(self, *args, **kvs)

        top_sizer = wx.BoxSizer(wx.VERTICAL)
        box_sizer = wx.BoxSizer(wx.VERTICAL)
        top_sizer.Add(box_sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 20)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="短时间休息间隔(分钟):"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        self.break_time_period_text_ctrl = wx.TextCtrl(self, value="%d"%(wx.Config.Get().ReadInt("break_time_period")//60))
        sizer.AddSpacer(5)
        sizer.Add(self.break_time_period_text_ctrl)
        box_sizer.Add(sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="短时间休息时间(秒):"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        self.break_time_text_ctrl = wx.TextCtrl(self, value="%d"%wx.Config.Get().ReadInt("break_time"))
        sizer.AddSpacer(5)
        sizer.Add(self.break_time_text_ctrl)
        box_sizer.Add(sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="长时间休息间隔(分钟):"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        self.long_break_time_period_text_ctrl = wx.TextCtrl(self, value="%d"%(wx.Config.Get().ReadInt("long_break_time_period")//60))
        sizer.AddSpacer(5)
        sizer.Add(self.long_break_time_period_text_ctrl)
        box_sizer.Add(sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="长时间休息时间(分钟):"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        self.long_break_time_text_ctrl = wx.TextCtrl(self, value="%d"%(wx.Config.Get().ReadInt("long_break_time")//60))
        sizer.AddSpacer(5)
        sizer.Add(self.long_break_time_text_ctrl)
        box_sizer.Add(sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="模式:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL)
        self.mode_combobox = wx.ComboBox(self, choices=["无", "客户端", "服务器"], style=wx.CB_READONLY)
        self.mode_combobox.SetSelection(wx.Config.Get().ReadInt("mode"))
        sizer.AddSpacer(5)
        sizer.Add(self.mode_combobox)
        box_sizer.Add(sizer, 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL, 5)

        box_sizer.AddSpacer(10)
        box_sizer.Add(self.CreateSeparatedButtonSizer(wx.OK|wx.CANCEL), 0, wx.ALIGN_CENTER_HORIZONTAL|wx.ALL)
        self.SetSizerAndFit(top_sizer)

    def TransferDataFromWindow(self):
        try:
            value = int(self.break_time_period_text_ctrl.GetValue())
            if value <= 0:
                return False
            wx.Config.Get().WriteInt("break_time_period",  value*60)

            value = int(self.break_time_text_ctrl.GetValue())
            if value <= 0:
                return False
            wx.Config.Get().WriteInt("break_time", value) 

            value = int(self.long_break_time_period_text_ctrl.GetValue())
            if value <= 0:
                return False
            wx.Config.Get().WriteInt("long_break_time_period", value*60)

            value = int(self.long_break_time_text_ctrl.GetValue())
            if value <= 0:
                return False
            wx.Config.Get().WriteInt("long_break_time", value*60)

            value = self.mode_combobox.GetSelection()
            wx.Config.Get().WriteInt("mode", value)

            wx.Config.Get().Flush()
            return True
        except ValueError:
            return False

class RSITaskBarIcon(adv.TaskBarIcon):

    def __init__(self):
        adv.TaskBarIcon.__init__(self)
        self.Bind(adv.EVT_TASKBAR_LEFT_DOWN, self.show_setting)
        self.is_show_dialog = False

    def CreatePopupMenu(self):
        break_timer = BreakTimer()
        popup_menu = wx.Menu()
        popup_menu.Append(wx.ID_ANY, "短休息还需%d分钟"%break_timer.get_break_time_remain()).Enable(False)
        popup_menu.Append(wx.ID_ANY, "长休息还需%d分钟"%break_timer.get_long_break_time_remain()).Enable(False)
        popup_menu.AppendSeparator()
        if break_timer.is_running():
            start_stop_menu = popup_menu.Append(wx.ID_ANY, "停止")
        else:
            start_stop_menu = popup_menu.Append(wx.ID_ANY, "开启")
        popup_menu.AppendSeparator()
        popup_menu.Append(wx.ID_EXIT, "&Exit")
        popup_menu.Bind(wx.EVT_MENU, self.do_exit, id=wx.ID_EXIT)
        popup_menu.Bind(wx.EVT_MENU, self.start_stop_break, start_stop_menu)
        return popup_menu

    def show_setting(self, event):
        if self.is_show_dialog:
            return

        self.is_show_dialog = True
        with SettingDialog(None) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                break_timer = BreakTimer()
                break_timer.read_config()
        self.is_show_dialog = False

    def start_stop_break(self, event):
        break_timer = BreakTimer()
        if break_timer.is_running():
            break_timer.stop()
        else:
            break_timer.start()

    def do_exit(self, event):
        wx.GetApp().ExitMainLoop()

class ScreenFrame(wx.Frame):

    def __init__(self, timeout_second):
        if wx.PlatformInfo[0] == "__WXGTK__":
            wx.Frame.__init__(self, None)
        else:
            wx.Frame.__init__(self, None, style=wx.STAY_ON_TOP|wx.FRAME_NO_TASKBAR)

        if timeout_second <= 0:
            self.Destroy()
            return

        self.timeout_second = timeout_second

        self.tip_label = wx.StaticText(self)
        font = self.tip_label.GetFont()
        font.SetPointSize(24)
        self.tip_label.SetFont(font)
        self.tip_label.SetForegroundColour("WHITE")
        self.tip_label.Bind(wx.EVT_LEFT_DOWN, self.on_skip)
        self.update_timer()

        sizer_horizontal = wx.BoxSizer(wx.HORIZONTAL)
        skip_link = wx.StaticText(self, label="跳过")
        font = skip_link.GetFont()
        font.SetPointSize(20)
        skip_link.SetFont(font)
        skip_link.Bind(wx.EVT_LEFT_DOWN, self.on_skip)

        bmp = wx.ArtProvider.GetBitmap(wx.ART_QUIT, wx.ART_OTHER)
        exit_bmp = wx.StaticBitmap(self, -1, bmp)
        sizer_horizontal.Add(skip_link, 0, wx.ALIGN_CENTER|wx.ALL)
        sizer_horizontal.Add(exit_bmp, 0, wx.ALIGN_CENTER|wx.ALL, border=10)

        sizer_vertical = wx.BoxSizer(wx.VERTICAL)
        sizer_vertical.AddStretchSpacer()
        sizer_vertical.Add(self.tip_label, 0, wx.ALIGN_CENTER|wx.ALL)
        sizer_vertical.AddStretchSpacer()
        sizer_vertical.Add(sizer_horizontal, 0, wx.ALIGN_CENTER|wx.ALL)
        sizer_vertical.AddStretchSpacer()
        self.SetSizer(sizer_vertical)

        self.timer = wx.Timer(self)
        # one seconds
        self.timer.Start(1000)
        self.Bind(wx.EVT_TIMER, self.on_second_timer, self.timer)

    def on_second_timer(self, event):
        self.timeout_second -= 1
        if self.timeout_second <= 0:
            self.timer.Stop()
            self.Destroy()
            return

        self.update_timer()

    def on_skip(self, event):
        self.timer.Stop()
        self.Destroy()

    def update_timer(self):
        if self.timeout_second > 60:
            self.tip_label.SetLabel("剩余%d分钟%d秒"%(self.timeout_second//60, self.timeout_second%60))
        else:
            self.tip_label.SetLabel("剩余%d秒"%self.timeout_second)

@singleton
class BreakTimer():
    TIMER_INTERVAL = 60*1000

    def __init__(self):
        self.minute = 0
        self.timer = None
        self.read_config()

    def init(self, parent):
        if not self.timer:
            self.timer = wx.Timer(parent)
            parent.Bind(wx.EVT_TIMER, lambda e: self.on_minute_timer(), self.timer)

    def start(self):
        self.timer.Start(self.TIMER_INTERVAL)

    def stop(self):
        self.timer.Stop()

    def is_running(self):
        return self.timer.IsRunning()

    def read_config(self):
        self.break_time_period_minute = wx.Config.Get().ReadInt("break_time_period")//60
        self.break_time_second = wx.Config.Get().ReadInt("break_time")
        self.long_break_time_period_minute = wx.Config.Get().ReadInt("long_break_time_period")//60
        self.long_break_time_second = wx.Config.Get().ReadInt("long_break_time")

    def get_break_time_remain(self):
        return self.break_time_period_minute - self.minute%self.break_time_period_minute 

    def get_long_break_time_remain(self):
        return self.long_break_time_period_minute - self.minute%self.long_break_time_period_minute 

    def create_screen_frame(self, break_time_second):
        for index in range(wx.Display.GetCount()):
            display = wx.Display(index)
            geo = display.GetGeometry()
            frame = ScreenFrame(break_time_second)
            frame.SetPosition((geo.x, geo.y))
            frame.ShowFullScreen(True)

    def on_minute_timer(self):
        self.minute += 1

        if self.minute % self.long_break_time_period_minute == 0:
            self.create_screen_frame(self.long_break_time_second)
            RSIService().brodcast_break(self.long_break_time_second)
        elif self.minute % self.break_time_period_minute == 0:
            self.create_screen_frame(self.break_time_second)
            RSIService().brodcast_break(self.break_time_second)

@singleton
class RSIService(Thread):

    MULTICAST_GRP = "224.0.0.222"
    MULTICAST_PORT = 9999

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.mode = wx.Config.Get().ReadInt("mode")
        if self.mode == MODE_CLIENT:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.MULTICAST_PORT))
            req = struct.pack("4sl", socket.inet_aton(self.MULTICAST_GRP), socket.INADDR_ANY)
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, req)
            self.start()

    def brodcast_break(self, time_second):
        if self.mode == MODE_SERVER:
            self.sock.sendto(struct.pack('cI', b'R', time_second), (self.MULTICAST_GRP, self.MULTICAST_PORT))

    def run(self):
        data_format_len = struct.calcsize('cI')
        while True:
            data = self.sock.recv(data_format_len)
            if data:
                try:
                   head, break_time = struct.unpack('cI', data)
                   if head != b'R':
                       print("ERR: invalid UDP head data")
                       continue

                   wx.CallAfter(pub.sendMessage, "break_time.listener", message=break_time)
                except struct.error:
                    print("ERR: invalid UDP data")

class MyRSIApp(wx.App):

    def __init__(self):
        wx.App.__init__(self)

    def OnInit(self):
        self.name = "RSI-%s" % wx.GetUserId()
        self.single_instance = wx.SingleInstanceChecker(self.name)

        if self.single_instance.IsAnotherRunning():
            wx.MessageBox("Another instance is running", "ERROR")
            return False

        config = wx.Config("myrsi")
        # 初始化配置
        if not config.HasEntry("break_time_period"):
            config.WriteInt("break_time_period", 20*60)
            config.WriteInt("break_time", 30)
            config.WriteInt("long_break_time_period", 60*60)
            config.WriteInt("long_break_time", 3*60)
            config.Flush()
        if not config.HasEntry("mode"):
            config.WriteInt("mode", MODE_NONE)
            config.Flush()
        wx.Config.Set(config)

        if adv.TaskBarIcon.IsAvailable():
            self.taskbar_icon = RSITaskBarIcon()
            if not self.taskbar_icon.SetIcon(
                    wx.ArtProvider.GetBitmapBundle(wx.ART_GO_HOME, wx.ART_OTHER),
                    "RSI for protect you eyes"):
                wx.MessageBox("Could not set task bar icon.", "ERROR")
                return False
        else:
            # don't exit when the top-level frame is deleted
            self.SetExitOnFrameDelete(False)

        break_timer = BreakTimer()
        break_timer.init(self)
        if wx.Config.Get().ReadInt("mode") == MODE_CLIENT:
            pub.subscribe(self.break_time_listener, "break_time.listener")
        else:
            break_timer.start()

        # Linux GTK 需要有一个topwindow才能运行
        if wx.PlatformInfo[0] == "__WXGTK__":
            ScreenFrame(1)

        RSI_service = RSIService()
        return True

    def break_time_listener(self, message):
        break_time_second = message
        if break_time_second > 0:
            break_timer = BreakTimer()
            break_timer.create_screen_frame(break_time_second)

def main(argv):
    MyRSIApp().MainLoop()
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
