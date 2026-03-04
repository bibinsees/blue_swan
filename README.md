Server: http://0.0.0.0:8000 (accessible on your local network)

URLs:

Page	URL
Player registration (via QR)	http://10.32.6.68:8000/
Game page (auto after register)	http://10.32.6.68:8000/game/{id}
Leaderboard (for main monitor)	http://10.32.6.68:8000/leaderboard
New admin page: http://10.32.6.68:8000/admin
To start the server next time:


cd c:/Users/Administrator/blue_swan
C:/ProgramData/anaconda3/python.exe main.py

new:
http://100.83.234.73:8000/
http://100.83.234.73:8000/leaderboard

new with laptop hotspot:
Game URL: http://192.168.137.1:8000/
Leaderboard: http://192.168.137.1:8000/leaderboard


# main branch
Its the basic version. where players can play only using local machine, that is only one player at the time.
# local_host branch
code is written such a way that server connection only works if the laptop's hotspot is turned on 

Tasks to be done 
more rules:
0. cant use the same username and email_id
1. make time out ie max time 2 minutes, after that automatically kill the process.
2. if its tie with token number use time used less.
3. ad conition in UI that cant use the same verb.
4. show the prompts worked in the leader board. but hide it only shows 
5. turn the ui into cairo theme.

