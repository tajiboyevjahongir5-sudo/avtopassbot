with open("index.html", "r", encoding="utf-8") as f:
    c = f.read()
c = c.replace("fetch(`/auth", "fetch(`${API}/auth")
c = c.replace("fetch(`/chats", "fetch(`${API}/chats")
c = c.replace("fetch(`/rules", "fetch(`${API}/rules")
with open("index.html", "w", encoding="utf-8") as f:
    f.write(c)
