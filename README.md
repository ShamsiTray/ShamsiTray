<div dir="ltr" align=center>
    
[**فارسی**](README.fa.md)
</div>

<div align="center">
  <img src="https://raw.githubusercontent.com/ShamsiTray/ShamsiTray/main/assets/images/icons/Logo.png" width="128" height="128" />
</div>

<h1 align="center">
	ShamsiTray
</h1>

<div align="center">
ShamsiTray is a lightweight Persian (Jalali/Shamsi) calendar app for Windows that displays the current day of the month in the system tray as an icon. It provides an intuitive calendar popup, a date conversion tool, holiday tracking, and the ability to add user events to dates.

### 
<a href="https://github.com/ShamsiTray/ShamsiTray/releases/download/v1.3/ShamsiTraySetup-1.3.exe">
  <img src="https://img.shields.io/badge/Download-Green?style=flat" width="150" />
</a>
<br>

[![Windows Only](https://custom-icon-badges.demolab.com/badge/Windows%20Only-0078D6?logo=windows11&logoColor=white)](#) [![Downloads](https://img.shields.io/github/downloads/ShamsiTray/ShamsiTray/total?style=flat&logo=github&label=Downloads&labelColor=27303D&color=0D1117)](#)

</div>

## 🖼️ Pictures
<img src="https://github.com/user-attachments/assets/16873e50-b1f1-4cae-8ccb-2407847159a8" width="320" />
<img src="https://github.com/user-attachments/assets/f7a33070-9abc-4ff7-88c8-b08f57b78770" width="500" />

## ✨ Features

- Shows the current Shamsi (Jalali) date in the system tray.
- Quick access to a small calendar popup.
- Displays detailed information in the tray icon tooltip, including day of the week, month and year, holidays, and user-added events.
- Includes a simple Shamsi(Jalali)–Gregorian date converter.
- Allows adding events with options for yearly recurrence, automatic deletion after the event date passes, and full edit/delete support.
- Provides a “Go to Date” option.
- The tray icon date color turns red on holidays and Fridays.
- Shows holiday or event details when hovering over a highlighted date in the calendar popup (red for holidays, green/blue for events).
- Uses a local holidays.json file for holiday data (years 1400–1411 included). Users can freely modify or add holidays.
- Includes a “Today” button to instantly jump back to the current date in the calendar popup.
- Clicking a date in the calendar popup reveals its Gregorian equivalent, and the display format can be toggled between numeric (e.g., 12/24/2025) and long-form (e.g., Dec 24, 2025).
- Option to launch at Windows startup.
- Dark and Light Themes (the light mode is not perfect since the app was mainly built for dark mode use).

## 💡 Usage Tips

- Single-click the tray icon to open the calendar popup.
- Right-click the tray icon for quick actions: Date Converter, Change Theme, Launch at Windows startup and Exit.
- Hover the mouse on the tray icon for the details tooltip.
- Hover the mouse on the days with holiday/event in the calendar popup to see the details.
- Right-clicking on a Date in the calendar popup allows you to add/edit and remove events.
- Right-clicking on the year at the top of the calendar popup allows you to use the feature "Go To Date".
- Left-clicking on the results in the date converter window copies them.

## 🐛 Known Issues

- The context menu’s bottom-right corner slightly exceeds the bounds; despite numerous attempts to fix it, none were successful. The issue is barely noticeable in dark mode and somewhat more visible in light mode.
- Tray icon for the date **23** slightly exceed bounds, though it’s barely noticeable.

## 📝 Notes
The concept of this app was inspired by the software [LeoMoon JalaliTray](https://leomoon.com/downloads/desktop-apps/leomoon-jalalitray/), but I found it lacking in features, so I kept adding more until I ended up with **ShamsiTray**. The calendar popup UI was inspired by [Widgetify](https://widgetify.ir/).

I think this app is mostly complete since it has all the features I need, which means I don’t plan to add any new features or updates anymore.  
I initially planned to use an API to fetch holiday reasons, but due to the lack of a stable and dependable API, I opted for a local, file-based implementation instead.

Also this app was almost entirely vibe-coded.

## 🛠️ Contributing

While I don’t actively plan new features, bug reports and small fixes are welcome.  
Feel free to open an issue or submit a pull request.

## 📜 License

This work is under an [MIT license](LICENSE)