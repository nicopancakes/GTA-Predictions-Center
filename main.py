#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import math
import shutil
from datetime import datetime
from pathlib import Path
from collections import Counter

BASE = Path(__file__).parent.resolve()
DATA = BASE / "pccg_data"
DATA.mkdir(exist_ok=True)
BACKUP = DATA / "backups"
BACKUP.mkdir(exist_ok=True)

ROULETTE_FILE = DATA / "roulette_history.json"
SLOTS_FILE = DATA / "slots_history.json" # stores your data so it can addon to past logs
HORSES_FILE = DATA / "horses_history.json"

RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
OVERDUE_WINDOW = 20
PICKS = 3            # 3 is how many numbers/entries each pick category shows


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path, default):
    import json
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def save_json(path, data):
    import json
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def color_of(n):
    if n == 0:
        return "green"
    return "red" if n in RED_NUMBERS else "black"


def parity_of(n):
    if n == 0:
        return None
    return "odd" if n % 2 == 1 else "even"


def high_low_of(n):
    if n == 0:
        return None
    return "low" if 1 <= n <= 18 else "high"
class RouletteDB:
    def __init__(self):
        self.spins = load_json(ROULETTE_FILE, [])

    def save(self):
        if len(self.spins) > 12000:
            self.spins = self.spins[-12000:]
        save_json(ROULETTE_FILE, self.spins)

    def add(self, number, color, money_bet, money_won, notes=""):
        profit = money_won - money_bet
        color_streak = 1
        parity_streak = 1
        hl_streak = 1
        if self.spins:
            prev = self.spins[-1]
            if prev.get("color") == color:
                color_streak = prev.get("color_streak", 1) + 1
            p_now, p_prev = parity_of(number), parity_of(prev.get("number"))
            if p_now is not None and p_now == p_prev:
                parity_streak = prev.get("parity_streak", 1) + 1
            h_now, h_prev = high_low_of(number), high_low_of(prev.get("number"))
            if h_now is not None and h_now == h_prev:
                hl_streak = prev.get("hl_streak", 1) + 1
        self.spins.append({
            "time": now(), "number": number, "color": color,
            "money_bet": money_bet, "money_won": money_won, "profit": profit,
            "notes": notes, "color_streak": color_streak,
            "parity_streak": parity_streak, "hl_streak": hl_streak,
        })
        self.save()

    def frequency(self):
        return Counter(s["number"] for s in self.spins)

    def color_counts(self):
        return Counter(s["color"] for s in self.spins)

    def recent(self, n=40):
        return list(reversed(self.spins[-n:]))

    def total_profit(self):
        return sum(s.get("profit", 0) for s in self.spins)

    def current_streaks(self):
        if not self.spins:
            return None
        last = self.spins[-1]
        return {
            "color": last.get("color"), "color_streak": last.get("color_streak", 1),
            "parity": parity_of(last.get("number")), "parity_streak": last.get("parity_streak", 1),
            "high_low": high_low_of(last.get("number")), "hl_streak": last.get("hl_streak", 1),
        }

    def chi_square(self):
        total = len(self.spins)
        if total < 37:
            return None, "Need at least 37 logged spins for a meaningful reading."
        freq = self.frequency()
        expected = total / 37.0
        chi2 = sum(((freq.get(n, 0) - expected) ** 2) / expected for n in range(37))
        if chi2 < 36:
            verdict = "looks consistent with a fair wheel."
        elif chi2 < 51.0:
            verdict = "mildly uneven, within normal variation"
        elif chi2 < 67.0:
            verdict = "noticeably uneven...still plausible at this sample size"
        else:
            verdict = "hmm..quite uneven for this sample size"
        return chi2, verdict

    def z_scores(self):
        total = len(self.spins)
        if total < 37:
            return {}
        freq = self.frequency()
        p = 1.0 / 37.0
        expected = total * p
        sd = math.sqrt(total * p * (1 - p))
        if sd == 0:
            return {}
        return {n: (freq.get(n, 0) - expected) / sd for n in range(37)}

    def suggest_numbers(self):
        """Top picks from logged spins only, capped at Picks each."""
        freq = self.frequency()
        total = len(self.spins)
        if total < 5:
            return None, "You Need at least 5 logged spins before picks appear :("

        hot = [n for n, c in freq.most_common(PICKS)]
        all_nums = list(range(0, 37))
        cold = [n for n, c in sorted(((n, freq.get(n, 0)) for n in all_nums),
                                      key=lambda x: (x[1], x[0]))[:PICKS]]
        recent_nums = [s["number"] for s in self.spins[-OVERDUE_WINDOW:]]
        overdue = [n for n in all_nums if n not in recent_nums][:PICKS]

        result = {"hot": hot, "cold": cold, "overdue": overdue}
        z = self.z_scores()
        if z:
            most_dev = sorted(all_nums, key=lambda n: -abs(z[n]))[:PICKS]
            result["most_deviated"] = [(n, z[n]) for n in most_dev]
        return result, None
RANK_VALUE = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
              "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11}


class CardInputError(ValueError):
    pass


def parse_cards(text):
    if not text or not text.strip():
        raise CardInputError("Enter at least one card..")
    raw = text.replace(",", " ").split()
    cards = []
    for tok in raw:
        r = tok.strip().upper()
        if r == "T":
            r = "10"
        if r not in RANK_VALUE:
            raise CardInputError("Unrecognized card?" % tok)
        cards.append(r)
    return cards


def compute_hand(cards):
    total = sum(RANK_VALUE[c] for c in cards)
    aces = cards.count("A")
    demoted = 0
    while total > 21 and demoted < aces:
        total -= 10
        demoted += 1
    is_soft = (aces - demoted) > 0
    return total, is_soft


HARD = {
    5:  {2:"H",3:"H",4:"H",5:"H",6:"H",7:"H",8:"H",9:"H",10:"H",11:"H"},
    6:  {2:"H",3:"H",4:"H",5:"H",6:"H",7:"H",8:"H",9:"H",10:"H",11:"H"},
    7:  {2:"H",3:"H",4:"H",5:"H",6:"H",7:"H",8:"H",9:"H",10:"H",11:"H"},
    8:  {2:"H",3:"H",4:"H",5:"H",6:"H",7:"H",8:"H",9:"H",10:"H",11:"H"},
    9:  {2:"H",3:"D",4:"D",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    10: {2:"D",3:"D",4:"D",5:"D",6:"D",7:"D",8:"D",9:"D",10:"H",11:"H"},
    11: {2:"D",3:"D",4:"D",5:"D",6:"D",7:"D",8:"D",9:"D",10:"D",11:"H"},
    12: {2:"H",3:"H",4:"S",5:"S",6:"S",7:"H",8:"H",9:"H",10:"H",11:"H"},
    13: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"H",8:"H",9:"H",10:"H",11:"H"},
    14: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"H",8:"H",9:"H",10:"H",11:"H"},
    15: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"H",8:"H",9:"H",10:"H",11:"H"},
    16: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"H",8:"H",9:"H",10:"H",11:"H"},
    17: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    18: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    19: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    20: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    21: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
}
SOFT = {
    13: {2:"H",3:"H",4:"H",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    14: {2:"H",3:"H",4:"H",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    15: {2:"H",3:"H",4:"D",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    16: {2:"H",3:"H",4:"D",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    17: {2:"H",3:"D",4:"D",5:"D",6:"D",7:"H",8:"H",9:"H",10:"H",11:"H"},
    18: {2:"S",3:"D",4:"D",5:"D",6:"D",7:"S",8:"S",9:"H",10:"H",11:"H"},
    19: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    20: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
}
PAIRS = {
    2:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"P",8:"H",9:"H",10:"H",11:"H"},
    3:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"P",8:"H",9:"H",10:"H",11:"H"},
    4:  {2:"H",3:"H",4:"H",5:"P",6:"P",7:"H",8:"H",9:"H",10:"H",11:"H"},
    5:  {2:"D",3:"D",4:"D",5:"D",6:"D",7:"D",8:"D",9:"D",10:"H",11:"H"},
    6:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"H",8:"H",9:"H",10:"H",11:"H"},
    7:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"P",8:"H",9:"H",10:"H",11:"H"},
    8:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"P",8:"P",9:"P",10:"P",11:"P"},
    9:  {2:"P",3:"P",4:"P",5:"P",6:"P",7:"S",8:"P",9:"P",10:"S",11:"S"},
    10: {2:"S",3:"S",4:"S",5:"S",6:"S",7:"S",8:"S",9:"S",10:"S",11:"S"},
    11: {2:"P",3:"P",4:"P",5:"P",6:"P",7:"P",8:"P",9:"P",10:"P",11:"P"},
}
ACTION_NAME = {"H": "HIT", "S": "STAND", "D": "DOUBLE", "P": "SPLIT", "?": "unknown"}


def advise(player_cards, dealer_up_card):
    du_val = RANK_VALUE[dealer_up_card]
    total, is_soft = compute_hand(player_cards)

    if len(player_cards) == 2 and player_cards[0] == player_cards[1]:
        row = PAIRS.get(RANK_VALUE[player_cards[0]])
        if row:
            a = row.get(du_val, "?")
            return a, ACTION_NAME.get(a, a), total, is_soft, True

    if is_soft:
        row = SOFT.get(total)
        if row:
            a = row.get(du_val, "?")
            return a, ACTION_NAME.get(a, a), total, is_soft, False

    row = HARD.get(total)
    if row:
        a = row.get(du_val, "?")
        return a, ACTION_NAME.get(a, a), total, is_soft, False
    if total > 21:
        return "?", "BUST", total, is_soft, False
    return "?", "No advice for that total.. Sorry..", total, is_soft, False
class SlotsDB:
    def __init__(self):
        self.spins = load_json(SLOTS_FILE, [])

    def save(self):
        if len(self.spins) > 12000:
            self.spins = self.spins[-12000:]
        save_json(SLOTS_FILE, self.spins)

    def add(self, machine, money_bet, money_won, notes=""):
        machine = machine.strip() or "Default"
        profit = money_won - money_bet
        self.spins.append({
            "time": now(), "machine": machine, "money_bet": money_bet,
            "money_won": money_won, "profit": profit, "notes": notes,
        })
        self.save()

    def recent(self, n=30):
        return list(reversed(self.spins[-n:]))

    def total_profit(self):
        return sum(s.get("profit", 0) for s in self.spins)

    def machine_stats(self):
        stats = {}
        for s in self.spins:
            m = s.get("machine", "Default")
            d = stats.setdefault(m, {"spins": 0, "bet": 0.0, "won": 0.0})
            d["spins"] += 1
            d["bet"] += s.get("money_bet", 0)
            d["won"] += s.get("money_won", 0)
        for d in stats.values():
            d["return_rate"] = (d["won"] / d["bet"]) if d["bet"] > 0 else 0.0
        return stats

    def top_machines(self, n=PICKS, min_spins=3):
        stats = self.machine_stats()
        eligible = [(m, d) for m, d in stats.items() if d["spins"] >= min_spins]
        eligible.sort(key=lambda x: -x[1]["return_rate"])
        return eligible[:n]

    def bottom_machines(self, n=PICKS, min_spins=3):
        stats = self.machine_stats()
        eligible = [(m, d) for m, d in stats.items() if d["spins"] >= min_spins]
        eligible.sort(key=lambda x: x[1]["return_rate"])
        return eligible[:n]
class HorseDB:
    def __init__(self):
        self.races = load_json(HORSES_FILE, [])

    def save(self):
        if len(self.races) > 12000:
            self.races = self.races[-12000:]
        save_json(HORSES_FILE, self.races)

    def add(self, winner, bet_on, money_bet, money_won, notes=""):
        profit = money_won - money_bet
        self.races.append({
            "time": now(), "winner": winner, "bet_on": bet_on,
            "money_bet": money_bet, "money_won": money_won, "profit": profit,
            "notes": notes,
        })
        self.save()

    def recent(self, n=30):
        return list(reversed(self.races[-n:]))

    def total_profit(self):
        return sum(r.get("profit", 0) for r in self.races)

    def winner_frequency(self):
        return Counter(r["winner"] for r in self.races)

    def hot(self, n=PICKS):
        return [num for num, c in self.winner_frequency().most_common(n)]

    def cold(self, n=PICKS):
        freq = self.winner_frequency()
        return [num for num, c in sorted(freq.items(), key=lambda x: x[1])[:n]]

    def bet_win_rate(self):
        bet_races = [r for r in self.races if r.get("bet_on")]
        if not bet_races:
            return None
        wins = sum(1 for r in bet_races if r.get("bet_on") == r.get("winner"))
        return wins / len(bet_races)
class PCCGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GTA Predictions Center")
        self.geometry("1120x760")
        self.minsize(950, 620)

        self.roulette = RouletteDB()
        self.slots = SlotsDB()
        self.horses = HorseDB()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        top = tk.Frame(self, relief=tk.RAISED, bd=1)
        top.pack(fill=tk.X)
        self.status = tk.StringVar(value="Welcome.")
        tk.Label(top, textvariable=self.status, anchor="w", padx=6).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(top, text="Save", command=self._save_all, width=8).pack(side=tk.RIGHT, padx=4, pady=2)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.tab_r = tk.Frame(self.nb)
        self.tab_bj = tk.Frame(self.nb)
        self.tab_stats = tk.Frame(self.nb)
        self.tab_others = tk.Frame(self.nb)

        self.nb.add(self.tab_r, text=" Roulette ")
        self.nb.add(self.tab_bj, text=" Blackjack ")
        self.nb.add(self.tab_stats, text=" Statistics ")
        self.nb.add(self.tab_others, text=" Others ")

        self._build_roulette()
        self._build_blackjack()
        self._build_stats()
        self._build_others()
    def _build_roulette(self):
        left = tk.Frame(self.tab_r, padx=6, pady=6)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        exp = tk.LabelFrame(left, text="How to use this page", padx=6, pady=4)
        exp.pack(fill=tk.X, pady=(0, 6))
        exp_text = (
            "1. After a spin finishes, type the winning number and pick the color.\n"
            "2. Money you put on the table = Money bet. Money you got back = Money won (just put 0 if you lost).\n"
            "3. Click Log This Spin.\n"
            "Nothing here predicts the next number* (Predictions can fail.)"
        )
        tk.Label(exp, text=exp_text, justify=tk.LEFT, anchor="w").pack(anchor="w")

        f = tk.LabelFrame(left, text="Enter the spin result", padx=6, pady=6)
        f.pack(fill=tk.X)

        tk.Label(f, text="Winning number (0-36):").grid(row=0, column=0, sticky="w")
        self.r_num = tk.Entry(f, width=8)
        self.r_num.grid(row=0, column=1, padx=4, sticky="w")
        self.r_num.bind("<KeyRelease>", self._auto_color)

        tk.Label(f, text="Color:").grid(row=0, column=2, sticky="w")
        self.r_color = ttk.Combobox(f, values=["red", "black", "green"], width=8, state="readonly")
        self.r_color.set("red")
        self.r_color.grid(row=0, column=3, padx=4, sticky="w")

        tk.Label(f, text="Money you bet:").grid(row=1, column=0, sticky="w")
        self.r_bet = tk.Entry(f, width=10)
        self.r_bet.insert(0, "1000")
        self.r_bet.grid(row=1, column=1, padx=4, sticky="w")

        tk.Label(f, text="Money you won back:").grid(row=1, column=2, sticky="w")
        self.r_won = tk.Entry(f, width=10)
        self.r_won.insert(0, "0")
        self.r_won.grid(row=1, column=3, padx=4, sticky="w")

        tk.Label(f, text="Optional note:").grid(row=2, column=0, sticky="w")
        self.r_notes = tk.Entry(f, width=30)
        self.r_notes.grid(row=2, column=1, columnspan=3, padx=4, sticky="w")

        tk.Button(f, text="Log This Spin", command=self._log_roulette, width=14).grid(row=3, column=0, columnspan=2, pady=8, sticky="w")

        rf = tk.LabelFrame(left, text="Last spins you logged", padx=4, pady=4)
        rf.pack(fill=tk.BOTH, expand=True)
        cols = ("time", "num", "color", "bet", "won", "profit", "streak")
        self.r_tree = ttk.Treeview(rf, columns=cols, show="headings", height=14)
        for c, t, w in [
            ("time", "Time", 70), ("num", "Number", 55), ("color", "Color", 55),
            ("bet", "Money bet", 80), ("won", "Money won", 80), ("profit", "Profit", 70),
            ("streak", "Color streak", 85)
        ]:
            self.r_tree.heading(c, text=t)
            self.r_tree.column(c, width=w, anchor="center")
        self.r_tree.pack(fill=tk.BOTH, expand=True)
        self._refresh_roulette_list()

        right = tk.Frame(self.tab_r, padx=6, pady=6)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        sug = tk.LabelFrame(right, text="Top Picks", padx=4, pady=4)
        sug.pack(fill=tk.X, pady=(0, 6))
        self.r_sug_text = tk.Text(sug, width=34, height=12, font=("Courier", 9))
        self.r_sug_text.pack(fill=tk.BOTH, expand=True)

        stat = tk.LabelFrame(right, text="Bias & Streaks", padx=4, pady=4)
        stat.pack(fill=tk.X, pady=(0, 6))
        self.r_stat_text = tk.Text(stat, width=34, height=8, font=("Courier", 9))
        self.r_stat_text.pack(fill=tk.BOTH, expand=True)

        ff = tk.LabelFrame(right, text="Frequency", padx=4, pady=4)
        ff.pack(fill=tk.BOTH, expand=True)
        self.r_freq_text = tk.Text(ff, width=34, height=14, font=("Courier", 9))
        self.r_freq_text.pack(fill=tk.BOTH, expand=True)

        self._refresh_roulette_freq()
        self._update_suggestions()
        self._update_roulette_stats()

    def _auto_color(self, event=None):
        try:
            n = int(self.r_num.get().strip())
            if 0 <= n <= 36:
                self.r_color.set(color_of(n))
        except ValueError:
            pass

    def _log_roulette(self):
        try:
            num = int(self.r_num.get().strip())
            if num < 0 or num > 36:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Winning number must be from 0 to 36, Buddy.")
            return
        color = self.r_color.get()
        try:
            money_bet = float(self.r_bet.get().replace(",", "") or 0)
            money_won = float(self.r_won.get().replace(",", "") or 0)
        except ValueError:
            messagebox.showerror("Error", "Money bet and money won must be numbers")
            return
        notes = self.r_notes.get().strip()
        self.roulette.add(num, color, money_bet, money_won, notes)
        self.status.set("Spin logged: number %d (%s)" % (num, color))
        self.r_num.delete(0, tk.END)
        self.r_won.delete(0, tk.END)
        self.r_won.insert(0, "0")
        self.r_notes.delete(0, tk.END)
        self._refresh_roulette_list()
        self._refresh_roulette_freq()
        self._update_suggestions()
        self._update_roulette_stats()

    def _refresh_roulette_list(self):
        self.r_tree.delete(*self.r_tree.get_children())
        for s in self.roulette.recent(35):
            bet = s.get("money_bet", 0)
            won = s.get("money_won", 0)
            profit = s.get("profit", won - bet)
            self.r_tree.insert("", "end", values=(
                s.get("time", "")[11:19], s.get("number", ""), s.get("color", ""),
                "%.0f" % bet, "%.0f" % won, "%+.0f" % profit,
                "%s x%d" % (s.get("color", "")[:1].upper(), s.get("color_streak", 1))
            ))

    def _refresh_roulette_freq(self):
        self.r_freq_text.delete("1.0", tk.END)
        freq = self.roulette.frequency()
        total = len(self.roulette.spins)
        lines = ["Total spins logged: %d\n\n" % total]
        if total == 0:
            lines.append("No spins logged yet.\n")
        else:
            z = self.roulette.z_scores()
            items = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
            if z:
                lines.append("%-6s %5s %6s %7s\n" % ("Num", "Cnt", "Pct", "z"))
                lines.append("-" * 28 + "\n")
                for num, cnt in items:
                    pct = 100.0 * cnt / total
                    lines.append("%-6s %5d %5.1f%% %7.2f\n" % (num, cnt, pct, z.get(num, 0)))
            else:
                lines.append("%-6s %5s %6s\n" % ("Num", "Cnt", "Pct"))
                lines.append("-" * 20 + "\n")
                for num, cnt in items:
                    pct = 100.0 * cnt / total
                    lines.append("%-6s %5d %5.1f%%\n" % (num, cnt, pct))
            cols = self.roulette.color_counts()
            lines.append("\nColors:\n")
            for c in ("red", "black", "green"):
                lines.append("  %-6s %4d\n" % (c, cols.get(c, 0)))
        self.r_freq_text.insert("1.0", "".join(lines))

    def _update_suggestions(self):
        self.r_sug_text.delete("1.0", tk.END)
        result, err = self.roulette.suggest_numbers()
        if err:
            self.r_sug_text.insert("1.0", err)
            return
        lines = []
        lines.append("Hot: %s\n" % ", ".join(str(n) for n in result["hot"]))
        lines.append("Cold: %s\n" % ", ".join(str(n) for n in result["cold"]))
        lines.append("Overdue (last %d): %s\n" % (OVERDUE_WINDOW, ", ".join(str(n) for n in result["overdue"])))
        if "most_deviated" in result:
            lines.append("Most off-average:\n")
            for n, zval in result["most_deviated"]:
                lines.append("  %-3s z=%+.2f\n" % (n, zval))
        lines.append("\nDescribes your data only.\nThe wheel has no memory.\n")
        self.r_sug_text.insert("1.0", "".join(lines))

    def _update_roulette_stats(self):
        self.r_stat_text.delete("1.0", tk.END)
        lines = []
        chi2, verdict = self.roulette.chi_square()
        if chi2 is None:
            lines.append(verdict + "\n\n")
        else:
            lines.append("Chi-square: %.1f\n%s\n\n" % (chi2, verdict))
        streaks = self.roulette.current_streaks()
        if streaks:
            lines.append("Color   : %s x%d\n" % (streaks["color"], streaks["color_streak"]))
            if streaks["parity"]:
                lines.append("Parity  : %s x%d\n" % (streaks["parity"], streaks["parity_streak"]))
            if streaks["high_low"]:
                lines.append("High/Low: %s x%d\n" % (streaks["high_low"], streaks["hl_streak"]))
        self.r_stat_text.insert("1.0", "".join(lines))
    def _build_blackjack(self):
        wrap = tk.Frame(self.tab_bj, padx=20, pady=20)
        wrap.pack(fill=tk.BOTH, expand=True)

        adv = tk.LabelFrame(wrap, text="Card Advisor", padx=12, pady=12)
        adv.pack(fill=tk.X, anchor="n")

        howto = (
            "Type each card you are holding, separated by commas.\n"
            "Number cards: just the number (2-10).   Face cards: K, Q, or J.   Ace: A.\n"
            "Examples of the Commas Format:  10, 6   /   16, K   /   16, Q   /   A, 7   /   8, 8"
        )
        tk.Label(adv, text=howto, justify=tk.LEFT, fg="gray20", font=("Courier", 9)).grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        tk.Label(adv, text="Your cards:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w")
        self.bj_cards = tk.Entry(adv, width=18, font=("Arial", 11))
        self.bj_cards.grid(row=1, column=1, padx=4, sticky="w")
        self.bj_cards.bind("<KeyRelease>", lambda e: self._preview_hand())

        tk.Label(adv, text="Dealer's up card:", font=("Arial", 10, "bold")).grid(row=1, column=2, sticky="w")
        self.bj_du = tk.Entry(adv, width=6, font=("Arial", 11))
        self.bj_du.grid(row=1, column=3, padx=4, sticky="w")
        self.bj_du.bind("<KeyRelease>", lambda e: self._preview_hand())

        self.bj_preview = tk.StringVar(value="Your total shows here as you type...")
        tk.Label(adv, textvariable=self.bj_preview, fg="gray30").grid(row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))

        tk.Button(adv, text="Ask Card Advisor", command=self._get_advice, width=12).grid(row=3, column=0, pady=10, sticky="w")
        self.bj_advice = tk.StringVar(value=" Enter your cards then click Ask.")
        tk.Label(adv, textvariable=self.bj_advice, font=("Courier", 16, "bold"), fg="darkblue").grid(row=3, column=1, columnspan=3, sticky="w")

    def _preview_hand(self):
        try:
            cards = parse_cards(self.bj_cards.get())
        except CardInputError:
            self.bj_preview.set("Your total shows here as you type...")
            return
        total, is_soft = compute_hand(cards)
        kind = "soft" if is_soft else "hard"
        if len(cards) == 2 and cards[0] == cards[1]:
            kind = "pair of %ss" % cards[0]
        self.bj_preview.set("Card Advisor Thinks... %s = %d (%s)" % (", ".join(cards), total, kind))

    def _get_advice(self):
        try:
            cards = parse_cards(self.bj_cards.get())
            du = parse_cards(self.bj_du.get())
            if len(du) != 1:
                raise CardInputError("Dealer up card should be a single card")
        except CardInputError as e:
            self.bj_advice.set("Fix input: %s" % e)
            return
        code, name, total, is_soft, is_pair = advise(cards, du[0])
        kind = "pair" if is_pair else ("soft" if is_soft else "hard")
        self.bj_advice.set(" Card Advisor says: %s   (total %d, %s, vs dealer %s)" % (name, total, kind, du[0]))
    def _build_stats(self):
        f = tk.Frame(self.tab_stats, padx=10, pady=10)
        f.pack(fill=tk.BOTH, expand=True)
        tk.Label(f, text="Roulette statistics", font=("Courier", 12, "bold")).pack(anchor="w")
        self.stats_text = tk.Text(f, font=("Courier", 10), height=28)
        self.stats_text.pack(fill=tk.BOTH, expand=True, pady=6)
        bf = tk.Frame(f)
        bf.pack(fill=tk.X)
        tk.Button(bf, text="Refresh", command=self._refresh_stats).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="Export Roulette CSV", command=self._export_roulette).pack(side=tk.LEFT, padx=4)
        tk.Button(bf, text="Backup files", command=self._backup).pack(side=tk.LEFT, padx=4)
        self._refresh_stats()

    def _refresh_stats(self):
        self.stats_text.delete("1.0", tk.END)
        lines = []
        lines.append("Spins logged : %d\n" % len(self.roulette.spins))
        lines.append("Total profit : %+.0f\n" % self.roulette.total_profit())
        chi2, verdict = self.roulette.chi_square()
        if chi2 is not None:
            lines.append("Chi-square   : %.1f (%s)\n" % (chi2, verdict))
        cols = self.roulette.color_counts()
        lines.append("Red          : %d\n" % cols.get("red", 0))
        lines.append("Black        : %d\n" % cols.get("black", 0))
        lines.append("Green        : %d\n\n" % cols.get("green", 0))
        lines.append("Data folder:\n  %s\n" % DATA)
        self.stats_text.insert("1.0", "".join(lines))

    def _export_roulette(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["time", "number", "color", "money_bet", "money_won", "profit",
                        "color_streak", "parity_streak", "hl_streak", "notes"])
            for s in self.roulette.spins:
                w.writerow([s.get("time", ""), s.get("number", ""), s.get("color", ""),
                            s.get("money_bet", 0), s.get("money_won", 0), s.get("profit", 0),
                            s.get("color_streak", ""), s.get("parity_streak", ""), s.get("hl_streak", ""),
                            s.get("notes", "")])
        messagebox.showinfo("Export", "Saved to %s" % path)

    def _backup(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for src in [ROULETTE_FILE, SLOTS_FILE, HORSES_FILE]:
            if src.exists():
                dst = BACKUP / ("%s_%s" % (src.stem, ts))
                shutil.copy2(src, dst)
        messagebox.showinfo("Backup", "Backup saved in %s" % BACKUP)
    def _build_others(self):
        sub = ttk.Notebook(self.tab_others)
        sub.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.tab_slots = tk.Frame(sub)
        self.tab_horses = tk.Frame(sub)
        sub.add(self.tab_horses, text=" Horse Racing ")
        self._build_slots()
        self._build_horses()

    def _build_slots(self):
        left = tk.Frame(self.tab_slots, padx=6, pady=6)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        exp = tk.LabelFrame(left, text="How to use this page", padx=6, pady=4)
        exp.pack(fill=tk.X, pady=(0, 6))
        tk.Label(exp, justify=tk.LEFT, anchor="w", text=(
            "1. Machine Names Don't affect Predictions.\n"
            "2. Enter what you bet and what you won back (0 if nothing).\n"
            "3. Click Log This Spin. Each spin is independent."
        )).pack(anchor="w")

        f = tk.LabelFrame(left, text="Enter the spin result", padx=6, pady=6)
        f.pack(fill=tk.X)
        tk.Label(f, text="Machine name (optional):").grid(row=0, column=0, sticky="w")
        self.sl_machine = tk.Entry(f, width=16)
        self.sl_machine.grid(row=0, column=1, padx=4, sticky="w")
        tk.Label(f, text="Money bet:").grid(row=1, column=0, sticky="w")
        self.sl_bet = tk.Entry(f, width=10)
        self.sl_bet.insert(0, "100")
        self.sl_bet.grid(row=1, column=1, padx=4, sticky="w")
        tk.Label(f, text="Money won back:").grid(row=1, column=2, sticky="w")
        self.sl_won = tk.Entry(f, width=10)
        self.sl_won.insert(0, "0")
        self.sl_won.grid(row=1, column=3, padx=4, sticky="w")
        tk.Label(f, text="Optional note:").grid(row=2, column=0, sticky="w")
        self.sl_notes = tk.Entry(f, width=30)
        self.sl_notes.grid(row=2, column=1, columnspan=3, padx=4, sticky="w")
        tk.Button(f, text="Log This Spin", command=self._log_slot, width=14).grid(row=3, column=0, pady=8, sticky="w")

        rf = tk.LabelFrame(left, text="Last spins you logged", padx=4, pady=4)
        rf.pack(fill=tk.BOTH, expand=True)
        cols = ("time", "machine", "bet", "won", "profit")
        self.sl_tree = ttk.Treeview(rf, columns=cols, show="headings", height=12)
        for c, t, w in [("time", "Time", 70), ("machine", "Machine", 100), ("bet", "Bet", 70),
                        ("won", "Won", 70), ("profit", "Profit", 70)]:
            self.sl_tree.heading(c, text=t)
            self.sl_tree.column(c, width=w, anchor="center")
        self.sl_tree.pack(fill=tk.BOTH, expand=True)
        self._refresh_slots_list()

        right = tk.Frame(self.tab_slots, padx=6, pady=6)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        sug = tk.LabelFrame(right, text="Top Picks", padx=4, pady=4)
        sug.pack(fill=tk.X, pady=(0, 6))
        self.sl_sug_text = tk.Text(sug, width=34, height=12, font=("Courier", 9))
        self.sl_sug_text.pack(fill=tk.BOTH, expand=True)
        ov = tk.LabelFrame(right, text="Overview", padx=4, pady=4)
        ov.pack(fill=tk.BOTH, expand=True)
        self.sl_ov_text = tk.Text(ov, width=34, height=8, font=("Courier", 9))
        self.sl_ov_text.pack(fill=tk.BOTH, expand=True)
        self._update_slots_panels()

    def _log_slot(self):
        try:
            bet = float(self.sl_bet.get().replace(",", "") or 0)
            won = float(self.sl_won.get().replace(",", "") or 0)
        except ValueError:
            messagebox.showerror("Error", "Bet and won must be numbers")
            return
        self.slots.add(self.sl_machine.get(), bet, won, self.sl_notes.get().strip())
        self.status.set("Slot spin logged")
        self.sl_won.delete(0, tk.END)
        self.sl_won.insert(0, "0")
        self.sl_notes.delete(0, tk.END)
        self._refresh_slots_list()
        self._update_slots_panels()

    def _refresh_slots_list(self):
        self.sl_tree.delete(*self.sl_tree.get_children())
        for s in self.slots.recent(30):
            self.sl_tree.insert("", "end", values=(
                s.get("time", "")[11:19], s.get("machine", ""),
                "%.0f" % s.get("money_bet", 0), "%.0f" % s.get("money_won", 0),
                "%+.0f" % s.get("profit", 0)
            ))

    def _update_slots_panels(self):
        self.sl_sug_text.delete("1.0", tk.END)
        top = self.slots.top_machines()
        bottom = self.slots.bottom_machines()
        lines = []
        if not top:
            lines.append("Need at least 3 spins on the\nsame machine name before picks\nappear.\n")
        else:
            lines.append("Best return so far:\n")
            for m, d in top:
                lines.append("  %-12s %.0f%%\n" % (m, d["return_rate"] * 100))
            lines.append("\nWorst return so far:\n")
            for m, d in bottom:
                lines.append("  %-12s %.0f%%\n" % (m, d["return_rate"] * 100))
        lines.append("\n \n")
        self.sl_sug_text.insert("1.0", "".join(lines))

        self.sl_ov_text.delete("1.0", tk.END)
        total = len(self.slots.spins)
        total_bet = sum(s.get("money_bet", 0) for s in self.slots.spins)
        total_won = sum(s.get("money_won", 0) for s in self.slots.spins)
        rr = (total_won / total_bet * 100) if total_bet > 0 else 0
        ov_lines = [
            "Spins logged : %d\n" % total,
            "Total bet    : %.0f\n" % total_bet,
            "Total won    : %.0f\n" % total_won,
            "Return rate  : %.1f%%\n" % rr,
            "Total profit : %+.0f\n" % self.slots.total_profit(),
        ]
        self.sl_ov_text.insert("1.0", "".join(ov_lines))

    def _build_horses(self):
        left = tk.Frame(self.tab_horses, padx=6, pady=6)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        exp = tk.LabelFrame(left, text="How to use this page", padx=6, pady=4)
        exp.pack(fill=tk.X, pady=(0, 6))
        tk.Label(exp, justify=tk.LEFT, anchor="w", text=(
            "1. After the race, type the winning horse's number.\n"
            "2. If you bet, type which horse number you bet on (blank if you didn't bet).\n"
            "3. Enter the bet amount and payout, then Log This Race."
        )).pack(anchor="w")

        f = tk.LabelFrame(left, text="Enter the race result", padx=6, pady=6)
        f.pack(fill=tk.X)
        tk.Label(f, text="Winning horse #:").grid(row=0, column=0, sticky="w")
        self.hr_winner = tk.Entry(f, width=8)
        self.hr_winner.grid(row=0, column=1, padx=4, sticky="w")
        tk.Label(f, text="You bet on # (optional):").grid(row=0, column=2, sticky="w")
        self.hr_bet_on = tk.Entry(f, width=8)
        self.hr_bet_on.grid(row=0, column=3, padx=4, sticky="w")
        tk.Label(f, text="Bet amount:").grid(row=1, column=0, sticky="w")
        self.hr_bet = tk.Entry(f, width=10)
        self.hr_bet.insert(0, "100")
        self.hr_bet.grid(row=1, column=1, padx=4, sticky="w")
        tk.Label(f, text="Payout received:").grid(row=1, column=2, sticky="w")
        self.hr_won = tk.Entry(f, width=10)
        self.hr_won.insert(0, "0")
        self.hr_won.grid(row=1, column=3, padx=4, sticky="w")
        tk.Label(f, text="Optional note:").grid(row=2, column=0, sticky="w")
        self.hr_notes = tk.Entry(f, width=30)
        self.hr_notes.grid(row=2, column=1, columnspan=3, padx=4, sticky="w")
        tk.Button(f, text="Log This Race", command=self._log_horse, width=14).grid(row=3, column=0, pady=8, sticky="w")

        rf = tk.LabelFrame(left, text="Last races you logged", padx=4, pady=4)
        rf.pack(fill=tk.BOTH, expand=True)
        cols = ("time", "winner", "bet_on", "bet", "won", "profit")
        self.hr_tree = ttk.Treeview(rf, columns=cols, show="headings", height=12)
        for c, t, w in [("time", "Time", 65), ("winner", "Winner", 55), ("bet_on", "Your pick", 65),
                        ("bet", "Bet", 65), ("won", "Won", 65), ("profit", "Profit", 65)]:
            self.hr_tree.heading(c, text=t)
            self.hr_tree.column(c, width=w, anchor="center")
        self.hr_tree.pack(fill=tk.BOTH, expand=True)
        self._refresh_horses_list()

        right = tk.Frame(self.tab_horses, padx=6, pady=6)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        sug = tk.LabelFrame(right, text="Top Picks", padx=4, pady=4)
        sug.pack(fill=tk.X, pady=(0, 6))
        self.hr_sug_text = tk.Text(sug, width=34, height=10, font=("Courier", 9))
        self.hr_sug_text.pack(fill=tk.BOTH, expand=True)
        ov = tk.LabelFrame(right, text="Overview", padx=4, pady=4)
        ov.pack(fill=tk.BOTH, expand=True)
        self.hr_ov_text = tk.Text(ov, width=34, height=8, font=("Courier", 9))
        self.hr_ov_text.pack(fill=tk.BOTH, expand=True)
        self._update_horses_panels()

    def _log_horse(self):
        winner = self.hr_winner.get().strip()
        if not winner:
            messagebox.showerror("Error", "Enter the winning horse number")
            return
        bet_on = self.hr_bet_on.get().strip()
        try:
            bet = float(self.hr_bet.get().replace(",", "") or 0)
            won = float(self.hr_won.get().replace(",", "") or 0)
        except ValueError:
            messagebox.showerror("Error", "Bet and payout must be numbers")
            return
        self.horses.add(winner, bet_on, bet, won, self.hr_notes.get().strip())
        self.status.set("Race logged: winner #%s" % winner)
        self.hr_winner.delete(0, tk.END)
        self.hr_bet_on.delete(0, tk.END)
        self.hr_won.delete(0, tk.END)
        self.hr_won.insert(0, "0")
        self.hr_notes.delete(0, tk.END)
        self._refresh_horses_list()
        self._update_horses_panels()

    def _refresh_horses_list(self):
        self.hr_tree.delete(*self.hr_tree.get_children())
        for r in self.horses.recent(30):
            self.hr_tree.insert("", "end", values=(
                r.get("time", "")[11:19], r.get("winner", ""), r.get("bet_on", ""),
                "%.0f" % r.get("money_bet", 0), "%.0f" % r.get("money_won", 0),
                "%+.0f" % r.get("profit", 0)
            ))

    def _update_horses_panels(self):
        self.hr_sug_text.delete("1.0", tk.END)
        total = len(self.horses.races)
        if total < 3:
            self.hr_sug_text.insert("1.0", "Need at least 3 logged races\nbefore picks appear.\n")
        else:
            hot = self.horses.hot()
            cold = self.horses.cold()
            lines = ["Hot winners: %s\n" % ", ".join(hot)]
            lines.append("Cold winners: %s\n\n" % ", ".join(cold))
            lines.append("Describes your data only.\n")
            self.hr_sug_text.insert("1.0", "".join(lines))

        self.hr_ov_text.delete("1.0", tk.END)
        win_rate = self.horses.bet_win_rate()
        lines = ["Races logged : %d\n" % total, "Total profit : %+.0f\n" % self.horses.total_profit()]
        if win_rate is not None:
            lines.append("Your pick win rate: %.1f%%\n" % (win_rate * 100))
        self.hr_ov_text.insert("1.0", "".join(lines))
    def _save_all(self):
        self.roulette.save()
        self.slots.save()
        self.horses.save()
        self.status.set("All data saved!")

    def _on_close(self):
        self._save_all()
        self.destroy()


if __name__ == "__main__":
    app = PCCGApp()
    app.mainloop()
