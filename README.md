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


new: used ngrok for public url so players can join using their own network. 
# Terminal 1 — start the tunnel
ngrok http 8000

# Copy the Forwarding URL, e.g. https://a1b2c3d4.ngrok-free.app
# Terminal 2 — start the game server
PUBLIC_URL=https://a1b2c3d4.ngrok-free.app python main.py

above was example. below one actually working in vs code powershell terminal:
$env:PUBLIC_URL="https://murmurous-shanta-rejoicingly.ngrok-free.dev"; C:/ProgramData/anaconda3/python.exe main.py

Admin: http://localhost:8000/admin
Leaderboard: http://localhost:8000/leaderboard




# main branch
Its the basic version. where players can play only using local machine, that is only one player at the time.
# local_host branch
code is written such a way that server connection only works if the laptop's hotspot is turned on 

Tasks to be done 
more rules:

5. turn the ui into cairo theme.
6. more closer means cosine distance calc need to be done. 
0. make first round simple then increase difficulty. 2. how many rounds/sessions/target sentence should be there?
1. make time out ie max time 2 minutes, after that automatically kill the process. Is it necessary task? if yes we do it after switching to nowlan mode
2. Add institution for the leader board


9. do word count so that they cant paste whole essay as prompt and try to crash the game.

### Decided not to:
7. Make lower case and upper case irrelevant while matching. because if its relavant player can easily give uppercase/lowercase in the prompt and just prompt to make it lower/upper (do the opposite to generate the answer)
8. Should we restrict encoding and decoding or - no becasue people can just give extra 'a' and ask remove 'a', so there is no way we force them to be creative like this "  if you add -, + you cant remove it using the Remove !: Bl!ue Sch!wan fliegt von Neu!schwanstein nach Schw!einfurt. Tharun said claude gave that answr. even if we do that then remove Z from all words can work. 


# input tokens calculated by  input_tokens = response.usage.prompt_tokens