# Future Features — Backlog (not implemented yet)

> Ye file un features ke liye hai jo discuss ho chuke hain, chahiye hain, par abhi
> implement nahi karne hain. Jab kaam karna ho, ye file padho aur relevant entry
> implement karo, phir yahan se hata do (ya "DONE" mark kar do with date).

---

## 1. Two-way Telegram bot — phone se commands bhejo, sirf notification na ho

**Discussed:** 2026-09-07

**Abhi kya hai:** `recon/notify.py` ka Telegram integration **one-way/outbound-only**
hai — bot sirf message bhej sakta hai (`send_telegram_alert()`), tumhare messages
sun/samajh nahi sakta. `getUpdates` API sirf ek-baar, setup wizard ke andar,
`chat_id` pakadne ke liye use hoti hai (`poll_for_chat_id()`) — uske baad koi
listener nahi chalta.

**Kya chahiye:** Phone se real commands bhej sako aur project unhe samjhe, jaise:
- `/status` — kaunse programs par kya chal raha hai (dashboard jaisa, `show_dashboard()`
  se data le sakta hai)
- `/pause <program>` / `/resume <program>` — daemon ko rok/chalu karo
- `/scan <program>` — remotely ek naya `[A]` hunt trigger karo
- `/findings <program>` — latest VERIFIED/NEEDS_MANUAL_CONFIRMATION candidates bhejo

**Kaise banega (rough design, implement karte waqt refine karna):**
1. `recon/notify.py` mein ek naya persistent listener function — `getUpdates` ko
   long-polling mode mein baar-baar call kare (`offset` param se already-read
   messages skip karte hue), naye messages ke liye check kare.
2. Command parser — message text ko `/command arg1 arg2` pattern se parse kare.
3. Command dispatch — har command ko corresponding Python function se jodo
   (`show_dashboard`'s Python equivalent, `daemon.py`'s pid-management functions,
   `run_zero_touch_hunt` ko subprocess se trigger karna, etc.)
4. Ye ek **persistent background process** hoga (jaise `daemon.py` hai) — apna khud
   ka `--telegram-listener` mode ya naya script `recon/telegram_bot.py` ban sakta hai.
   `start-bugbounty.sh`'s daemon_menu jaisa hi ek start/stop/status mechanism chahiye.
5. **Security zaroori:** sirf `TELEGRAM_CHAT_ID` (jo setup wizard ne save kiya) se
   aaye commands accept karo — koi aur chat_id se command bheje to ignore karo,
   warna koi bhi tumhara bot dhoondh ke commands bhej sakta hai.
6. Real, destructive commands (jaise "submit report", "delete program") in mein
   **kabhi nahi hone chahiye** — human-gate rule yahan bhi apply hoga, phone se
   sirf read-only status ya safe-to-repeat actions (scan trigger, pause/resume)
   allow karna.

**Priority:** Medium — nice-to-have, existing one-way alerts already useful hain.

---

*(Naye backlog items yahan neeche add karte raho jaise discuss hon.)*
