<div align="center" >
	<img src="assets/icons/Logo.png" width="128px" height="128px"/>
</div>

<h1 align="center">
	ShamsiTray
</h1>

<div align="center">
ShamsiTray is a lightweight application for Windows that displays the current Persian (Jalali/Shamsi) day of the month in the system tray as an icon. It provides an intuitive calendar popup, a date conversion tool, holiday tracking, and the ability to add user events to dates.

###
<a href="https://github.com/ShamsiTray/ShamsiTray/releases/download/v1.2/ShamsiTraySetup-1.2.exe">
  <img src="https://img.shields.io/badge/Download-Green?style=flat" width="150" />
</a>
</div>

## Pictures
<img src="https://github.com/user-attachments/assets/16873e50-b1f1-4cae-8ccb-2407847159a8" width="320" />
<img src="https://github.com/user-attachments/assets/f7a33070-9abc-4ff7-88c8-b08f57b78770" width="500" />

## Features

- Shows the current Shamsi (Jalali) date in the system tray.
- Quick access to a small calendar popup.
- Displays detailed information in the tray icon tooltip, including day of the week, month and year, holidays, and user-added events.
- Includes a simple Shamsi(Jalali)–Gregorian date converter.
- Allows adding events. has an option for yearly recurring events, auto deleting event when the date of the event is passe and you can edit or delete events.
- Provides a “Go to Date” option (supports years 1200–1600).
- The tray icon date color turns red on holidays and Fridays.
- Shows holiday or event details when hovering over a highlighted date in the calendar popup (red for holidays, green/blue for events).
- Uses a local holidays.json file for holiday data (years 1400–1411 included). Users can freely modify or add holidays.
- Includes a “Today” button to instantly jump back to the current date in the calendar popup.
- Clicking a date in the calendar popup reveals its Gregorian equivalent, and the display format can be toggled between numeric (e.g., 12/24/2025) and long-form (e.g., Dec 24, 2025).
- Option to launch at Windows startup.
- Dark and Light Themes (not perfect since the app was mainly built for dark mode use).

## Usage Tips

- Single-click the tray icon to open the calendar popup.
- Right-click the tray icon for quick actions: Date Converter, Change Theme, Launch at Windows startup and Exit.
- Hover the mouse on the tray icon for the details tooltip.
- Right-clicking on a Date in the calendar popup allows you to add/edit and remove events.
- Right-clicking on the year at the top of the calendar popup allows you to use the feature "Go To Date".

## Known Issues

- The month dropdown in the **Go To Date** window may behave incorrectly on Windows 10 (It works normally on Windows 11).  
Temporary workarounds are: Click the far-left edge of the dropdown (sometimes restores correct behavior) or Use the mouse wheel to scroll through the months
- Date Converter day dropdown requires two clicks in certain cases: If you change the month before selecting a day, the day dropdown may need to be opened once before it starts working normally. After opening it once, the dropdown behaves correctly. This is likely related to how the list of days is recalculated when the selected month changes.
- Tray icons for the dates 23 and 25 goes out of bounds a bit but it's not really noticeable

## Notes
The concept of this app was inspired by the software [LeoMoon JalaliTray](https://leomoon.com/downloads/desktop-apps/leomoon-jalalitray/), but I found it lacking in features, so I kept adding more until I ended up with **ShamsiTray**. The calendar popup UI was inspired by [Widgetify](https://widgetify.ir/).

I think this app is mostly complete since it has all the features I need, which means I don’t plan to add any new features or updates anymore. The only thing I might add (emphasis on might) is an API-based fallback for Holiday Reasons, but don’t hold your breath.

Also this app was almost entirely vibe-coded.

## License

This work is under an [MIT license](LICENSE)
