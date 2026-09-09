# Mera Hunting Manual — Har Command, Exactly Kaise Chalayein

> Ye file tumhare khud ke istemal ke liye hai. **Har jagah exact command diya hai —
> jo `$` ke baad likha hai, wahi type karo (ya copy-paste karo) aur Enter dabao.**
> `<...>` wali cheez ko apni value se replace karna hai (jaise `<naam>` ki jagah
> `meesho` likhna).

---

# HISSA 0 — Terminal Kholna (bilkul shuruaat se)

1. Keyboard mein **`Ctrl` + `Alt` + `T`** dabao — ek kaala/terminal window khulega
   (agar ye kaam na kare, "Terminal" app dhoondo apne computer ke apps mein aur click karo)
2. Ab tumhare saamne kuch aisa dikhega: `mohit@computer:~$` — yahi terminal hai,
   yahi cursor blink kar raha hoga, yahin type karna hai

## Project folder mein jaana (har baar sabse pehle ye karna hai)
```
$ cd ~/Desktop/projects/bug-bounty
```
- `cd` matlab "change directory" (folder badlo)
- Enter dabane ke baad kuch print nahi hoga, bas naya line aayega — iska matlab
  successful hai. Confirm karne ke liye:
```
$ pwd
```
Isse print hona chahiye: `/home/mohit/Desktop/projects/bug-bounty`

---

# HISSA A — Tool Chalana (Command-by-Command)

## A1. Poora TUI (menu-wala) launcher chalana
```
$ ./start-bugbounty.sh
```
- `./` matlab "isi folder mein jo file hai use chalao"
- Enter dabate hi ek colorful menu-screen khulega
- Menu mein jo bhi option chahiye uska **letter/number type karke Enter dabao**
  (jaise `N` type karke Enter — matlab "New Scan" option select hua)
- Bahar niklne ke liye: `Q` type karo, Enter dabao

**Agar error aaye** `bash: ./start-bugbounty.sh: Permission denied`:
```
$ chmod +x start-bugbounty.sh
```
(ye ek hi baar karna padta hai, uske baad hamesha chalega)

---

## A2. Account banana (terminal se seedha, bina menu ke)
```
$ python3 recon/account_client.py --register --email tumhara@email.com --password TumhaPassword123
```
- `python3` = Python program chalane ka command
- `recon/account_client.py` = konsi file chalani hai
- `--register` = "naya account banao" (login karne ke liye `--login` likho isi jagah)
- `--email` ke baad apna email, `--password` ke baad apna password (kam se kam 8 letters)

**Expected output:** `Account bana (free tier). Login ho gaye.`

Status check karna ho to:
```
$ python3 recon/account_client.py --status
```

---

## A3. HackerOne credentials terminal se set karna
Pehle ek file banao (sirf ek baar karna hai):
```
$ nano .env.h1
```
(`nano` ek text-editor hai jo terminal ke andar hi khul jaata hai)

Usme ye likho (apni real values ke saath):
```
export H1_USERNAME="tumhara_h1_username"
export H1_API_TOKEN="tumhara_api_token"
```
Save karne ke liye: **`Ctrl+O`** dabao, phir **Enter**, phir band karne ke liye **`Ctrl+X`**

Ab load karo:
```
$ source .env.h1
```

Test karo ki sahi hai:
```
$ python3 recon/h1_client.py --test-auth
```
**Expected output:** `Authentication successful (HTTP 200)`

---

## A4. Naye HackerOne programs dhoondhna (terminal se)
```
$ python3 recon/h1_client.py --list --bounty-only --sort-recency --verbose --json
```
- `--list` = programs ki list nikalo
- `--bounty-only` = sirf paise dene wale programs (VDP wale nahi)
- `--sort-recency` = sabse naye programs pehle dikhao (kam-crowded)
- `--verbose` = progress dikhao terminal mein
- `--json` = poori detail JSON format mein print karo

Output mein sabse **upar wale** programs sabse naye hain — `"handle": "xyz"` wali
line mein program ka naam milega, wahi aage use karna hai.

---

## A5. Naya program setup karna (real scope H1 se sync karke)
```
$ python3 recon/h1_client.py --setup <program_handle> --folder <program_handle>
```
Example (agar handle `wolt` hai):
```
$ python3 recon/h1_client.py --setup wolt --folder wolt
```
**Expected output:**
```
[h1_client] Target folder: .../wolt
[h1_client] Retrieved N structured scope items from HackerOne.
[h1_client] Created .../wolt/scope.yaml
[h1_client] Target 'wolt' successfully configured: Roots: N | Excluded: N | Assets: N
```
Scope check karne ke liye:
```
$ cat wolt/scope.yaml
```
(`cat` matlab "file ka content dikhao")

---

## A6. Recon chalana (subdomains/live-hosts dhoondhna)
```
$ python3 recon/recon_pipeline.py --program <naam> --skip-js
```
- `--skip-js` = JavaScript-crawling skip karo (fast hota hai, endpoints kam milte hain)
- Isko hatana ho (poora crawl chahiye) to bas `--skip-js` mat likho

**Ye command 5-30 minute tak chal sakta hai** (target par depend karta hai) —
terminal mein progress dikhta rahega, khatam hone tak wait karo. Agar bahut zyada
time lag raha hai aur band karna ho: **`Ctrl+C`** dabao.

**Expected output ke aakhir mein:**
```
[recon] ✓ N active assets validated. assets.json written (Contract: VALID).
[recon] Done. Run ID: run_...
```

---

## A7. Candidates ko score/rank karna
```
$ python3 recon/intelligence.py --program <naam> --top 40
```
**Expected output:**
```
[intel] candidate_findings (score>=40): N
[intel] 🏆 TOP HIGH-VALUE ATTACK SURFACES (5 shown):
  1. [ 85] [tag] https://...
```
Number `[ 85]` = score (jitna zyada utna zyada interesting).

Poori report file mein dekhni ho:
```
$ cat recon/data/<naam>/candidate_report.md
```

---

## A8. Real verification chalana (auto_hunter)
```
$ python3 recon/auto_hunter.py --program <naam> --min-score 40
```
- `--min-score 40` = sirf 40+ score wale candidates check karo (kam number
  = zyada candidates check honge, zyada time lagega)
- Ek baar mein **max 50 candidates** check hote hain — agar zyada hain to
  **wahi command dobara chalao**, agla batch (jo pehle check nahi hua) apne aap check hoga

**Expected output ke aakhir mein:**
```
[auto_hunter] Finished. N verified findings confirmed out of 50 candidates.
```
Agar `N` zero se zyada hai, upar scroll karo — `✓ VERIFIED` wali green line
dikhegi poori detail ke saath (URL, kya mila, kitna severe).

---

## A9. Real nuclei vulnerability-scan chalana
```
$ NUCLEI_MAX_HOST_ERROR=3 NUCLEI_TIMEOUT=5 python3 recon/scanner.py --program <naam>
```
- `NUCLEI_MAX_HOST_ERROR=3 NUCLEI_TIMEOUT=5` = command se pehle likhne se
  scanner ko fast/safe settings milti hain (WordPress wale purane experience
  se seekha — bina isके bahut slow ho sakta hai)
- Ye bhi time le sakta hai (kitne hosts hain us par depend)

---

## A10. Poora automatic hunt (sab kuch ek command mein — sabse aasan)
```
$ ./start-bugbounty.sh --auto <naam>
```
Ye recon + scan + verify + report-draft sab khud-ba-khud kar deta hai, koi
menu navigate nahi karna padta. Fresh (cache ignore karke) chalana ho:
```
$ ./start-bugbounty.sh --auto <naam> --fresh
```

---

## A11. Kya chal raha hai, check karna
Kaunse background-processes chal rahe hain:
```
$ ps aux | grep python3
```
Ek specific program ke candidates ka status (kitne VERIFIED/REJECTED/TRIAGED):
```
$ python3 -c "
import sqlite3
con = sqlite3.connect('recon/data/<naam>/recon.db')
cur = con.cursor()
print(cur.execute(\"SELECT status, COUNT(*) FROM candidate_findings GROUP BY status\").fetchall())
"
```
(Isme `<naam>` ki jagah apna program-name likhna, jaise `meesho`)

---

# HISSA B — Manual Browser-Testing (Command + Click dono)

## B1. Apna Auth-Cookie nikalna
1. Website mein login karo (browser mein, normal tareeke se)
2. **F12 dabao** → DevTools khulega
3. **"Network"** tab par click karo (top mein kai tabs honge, ye ek dhoondo)
4. **F5 dabao** (page refresh) — ab list mein requests aayengi
5. Top mein agar **"Fetch/XHR"** button dikhe to usko click karo (list chhoti ho jayegi)
6. List mein se **koi bhi ek row** click karo
7. Right/neeche khulne wale panel mein **"Headers"** tab click karo
8. Neeche scroll karo — **"Request Headers"** section mein `Cookie:` line dhoondo
9. Uske aage jo lamba text hai (`abc=123; xyz=456; ...` jaisa) — **poora select karke copy karo** (`Ctrl+C`)

## B2. Cookie ko tool mein terminal se set karna
```
$ nano <program_naam>/.env.auth
```
Isme likho (apna cookie paste karke):
```
export AUTH_HEADER="Cookie"
export AUTH_VALUE="yahan_apna_copy_kiya_cookie_paste_karo"
```
Save: `Ctrl+O` → `Enter` → `Ctrl+X`

Permission secure karo (zaroori hai):
```
$ chmod 600 <program_naam>/.env.auth
```

Ab dobara auto_hunter chalao (A8 wala command) — ab authenticated-check bhi hoga.

## B3. Manual IDOR-test (browser mein seedha)
1. Apna real ID pata karo (login karke, URL ya DevTools se)
2. Doosra real ID dhoondo (kisi doosre user/product ka, public page se)
3. Apne **logged-in tab** mein, address-bar mein doosre-ID wala URL type karke Enter dabao
4. Dekho: doosre ka data dikhta hai (bug!) ya apna hi data/access-denied dikhta hai (safe)

## B4. Agar script se 403/Access-Denied mile
Ye WAF/bot-protection hai, real security-check nahi. Command se test karne ka
tareeka (agar karna ho — advanced):
```
$ python3 -c "
import sys
sys.path.insert(0, 'recon')
import auto_hunter
creds = auto_hunter.load_auth_credentials('<naam>')
status, headers, body = auto_hunter.safe_request('<poora_url_yahan>', headers={creds['AUTH_HEADER']: creds['AUTH_VALUE']})
print(status, body[:300])
"
```
Agar ye bhi 403 de (apne hi ID ke liye bhi), to **B3 wala manual browser-test**
hi bharosemand hai, script wala nahi.

---

# Sabse Zyada Use Hone Wale Commands (Quick Copy-Paste List)

```
cd ~/Desktop/projects/bug-bounty          # folder mein jao
./start-bugbounty.sh                       # poora menu-tool kholo
./start-bugbounty.sh --auto <naam>         # ek command mein poora hunt
python3 recon/h1_client.py --list --bounty-only --sort-recency --json   # naye programs
python3 recon/h1_client.py --setup <naam> --folder <naam>               # naya program setup
python3 recon/recon_pipeline.py --program <naam> --skip-js              # recon
python3 recon/intelligence.py --program <naam> --top 40                 # scoring
python3 recon/auto_hunter.py --program <naam> --min-score 40            # verify
```

---

# Zaroori Yaad Rakhne Wali Baatein
1. Sirf authorized targets (`scope.yaml` mein jo hai) par test karo.
2. `VERIFIED` = real check ho chuka hai, bharosa kar sakte ho (par H1 submit
   se pehle khud ek baar dekh lena).
3. `0 verified` bhi normal result hai — har scan mein kuch nahi milta, naye
   programs try karte raho.
4. Cookie/password kabhi kisi ko mat do, na chat mein bhejo.
5. Kuch samajh na aaye to `./start-bugbounty.sh` chala ke `D` (Diagnostics) dekho.



# Mera Hunting Manual — Poori Guide (Tool + Manual Testing)

> Ye file tumhare khud ke istemal ke liye hai — jab bhi bhool jao ki kya karna hai,
> yahi file padh lena. Do hisso mein hai: (A) Tool kaise use karo, (B) Manual
> browser-testing kaise karo (jab tool khud check nahi kar sakta).

---

# HISSA A — Tool Kaise Chalayein

## A1. Tool start karna
Terminal kholo, project-folder mein jao, aur ye command chalao:
```bash
cd ~/Desktop/projects/bug-bounty
./start-bugbounty.sh
```
Ek Mission-Control menu khulega. Pehli baar chalane par ek **onboarding wizard**
aayega (account banao, HackerOne credentials daalo) — sab kuch skip bhi kar
sakte ho `[0]` dabake, baad mein Main-Menu se kar sakte ho.

## A2. Pehli baar setup (agar abhi tak nahi kiya)
1. **Account banao** — Main Menu → `[A]` → Register → email/password daalo.
   (Ye tumhara apna login hai, subscription/quota track karne ke liye.)
2. **HackerOne credentials daalo** — Main Menu → `[H]` → apna H1 username +
   API token daalo. Token yahan se milta hai: `hackerone.com/settings/api_token`

## A3. Naya program add karna (3 tarike)
Main Menu → `[N]` (Start New Scan):
- **Option 1** — Cash Bounty wale programs (paisa milta hai)
- **Option 2** — Sab programs (paid + VDP, VDP mein paisa nahi milta)
- **Option 3** — Manual handle (agar tumhe pehle se pata hai program ka naam)
- **Option 4** — **Naye/kam-crowded programs** (recency se sort, kam competition ka chance)
- **Option 5** — Company/apna domain (agar HackerOne program nahi hai, apni khud ki site)

Jo program pasand aaye, uska number/handle daal do — automatically scope.yaml
ban jayega (agar H1-authorized program hai, real scope H1 se sync hoga).

## A4. Scan chalana
Jab target select ho jaye (Main Menu mein number dabake), Target Menu khulega:
- **`[A]` Autonomous Zero-Touch Hunt** — sabse aasan, sab kuch khud-ba-khud
  (recon → scan → verify → report-draft). **Yahi sabse zyada use karo.**
- **`[C]` Complete Scan + OpenCode Prompt** — jaisa `[A]`, plus ek AI-agent
  ke liye ready prompt bhi banata hai deeper manual review ke liye
- Individual modules (`[2]` Recon Only, `[3]` JS Miner, `[4]` Nuclei Scan) —
  sirf tab use karo jab ek hi specific step dobara chalana ho

## A5. Results kaise dekho
- **`[5]` View Candidate Report** — top-40 scored possible-leads ki list
- **`[V]` Dashboard** (Main Menu se) — sab programs ka ek-jagah summary
- Har candidate ka ek **status** hota hai:
  - `TRIAGED` = abhi tak check nahi hua
  - `VERIFIED` = tool ne confirm kiya real hai (real check ke saath, fabricate nahi karta)
  - `REJECTED` = check kiya, real nahi nikla (false-positive nahi)
  - `NEEDS_MANUAL_CONFIRMATION` = tool ko shak hai par pakka nahi (jaise IDOR) — **tumhe khud check karna hai**

## A6. Terminal se seedha command bhi chala sakte ho
```bash
python3 recon/auto_hunter.py --program <naam> --min-score 40   # verify candidates
python3 recon/intelligence.py --program <naam> --top 40         # scoring/ranking
python3 recon/scanner.py --program <naam>                       # real nuclei scan
```

---

# HISSA B — Manual Browser-Testing (jab tool khud nahi kar sakta)

Kuch cheezein (jaise IDOR — "kya main kisi aur ka data dekh sakta hoon") sirf
**tumhare khud ke real, logged-in session** se test ho sakti hain. Tool sirf
"ye check karne layak hai" bata sakta hai, asli test tumhe karna padta hai.

## B1. Apna Auth-Cookie nikalna (Chrome/Firefox mein same hai)
1. Us website mein **login karo** (apne khud ke ya authorized test account se)
2. Keyboard par **F12 dabao** — neeche/side mein DevTools panel khulega
3. Us panel ke top mein **"Network"** tab par click karo
4. Panel khali hoga — ab page **refresh karo (F5)** ya koi menu-item click karo
   (naya request generate karne ke liye)
5. Ek list aayegi requests ki — koi bhi ek (jo `.js`/`.png`/`.css` na ho) click karo
   (top mein "Fetch/XHR" filter bhi hota hai, usse list chhoti ho jaati hai)
6. Right/neeche panel khulega — usme **"Headers"** tab par click karo
7. Neeche scroll karo "**Request Headers**" section tak — `Cookie:` se shuru
   hone wali line dhoondo — uske aage jo lamba text hai, **wahi copy karo**

⚠️ **Ye cookie ek password jaisa hi sensitive hai** — kisi ko mat bhejo, aur agar
kabhi chat/message mein bhej diya to us session ko baad mein logout/refresh
karke naya bana lena achha rehta hai.

## B2. Cookie ko tool mein set karna
```bash
./start-bugbounty.sh
```
Target select karo → option **`[8]`** ("Set Up Authenticated Test Account") →
`[2] Cookie` choose karo → paste kar do jo copy kiya tha.

Ab `auto_hunter.py` is program ke liye authenticated-IDOR-check bhi karega
(sirf numeric IDs ke liye automatic — jaise `/user/123/orders`).

## B3. Alphanumeric-ID wala manual test (jaisa Meesho ke `3hy5q` ke liye kiya)
Agar ID number nahi hai (jaise `3hy5q`, `abc123` type), to tool khud test
nahi kar sakta (ID+1/ID-1 sirf numbers ke liye kaam karta hai). Ye khud karo:

1. **Apna real ID pata karo** — apne account mein login karke, URL ya
   DevTools mein dikhega (jaise `Supplier_id: kq15b`)
2. **Doosra real ID dhoondo** — kisi doosre user/product ka ID dhoondo
   (public page dekh ke, ya recon-data se — `candidate_report.md` mein
   milta hai kai baar)
3. **Apne logged-in browser tab mein**, us doosre-ID wala URL seedha khol do
   (address-bar mein type karke, Enter dabao)
4. Dekho kya hota hai:
   - **Doosre ka real data dikhta hai** → real bug mila, H1 par report karo
   - **Apna hi data dikhta hai, ya "not authorized", ya redirect ho jaata hai**
     → protected hai, koi bug nahi — ye bhi ek valid result hai, time waste nahi hua

## B4. Agar script se test karo to Access-Denied/403 mile
Kabhi kabhi WAF/bot-protection (jaise Akamai) script-wale requests ko block
kar deta hai, chahe login sahi ho. Agar `curl`/Python-script se test karte
waqt 403 "Access Denied" milta hai (apne hi ID ke liye bhi), to iska matlab
security-bug nahi hai — sirf bot-protection block kar raha hai. **Real browser
mein manually check karo** (Step B3 jaisa), wahi bharosemand result dega.

---

# Zaroori Yaad Rakhne Wali Baatein

1. **Sirf authorized targets par test karo** — `scope.yaml` mein jo hai sirf wahi.
2. **VERIFIED ka matlab hai tool ne real check kiya hai** — fabricate/jhoothi
   report kabhi nahi hoti is tool se, isiliye jo bhi VERIFIED mile uspe bharosa
   kar sakte ho, par H1 par submit karne se pehle khud ek baar zaroor dekh lo.
3. **REJECTED/0-verified bhi ek valid result hai** — har scan mein kuch na
   kuch milega zaroori nahi, ye normal hai, dobara try karte raho naye
   programs (Option 4, kam-crowded) ke saath.
4. **Cookie/password kabhi kisi ko mat do** — na chat mein, na kahi aur.
5. Agar kuch samajh na aaye, `Main Menu → [D]` (System Diagnostics) dekho —
   sab tools/credentials ka status ek jagah dikhta hai.
