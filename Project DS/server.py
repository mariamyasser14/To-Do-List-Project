
import json
import uuid
import os
from datetime import datetime
from flask import Flask, request, jsonify, Response, send_from_directory
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


app = Flask(__name__, static_folder="static", static_url_path="")

# ─── Database setup ──────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///tasks.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Task(Base):
    __tablename__ = "tasks"
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    priority = Column(String, default="medium")
    category = Column(String, default="General")
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ─── CORS helper ────────────────────────────────────────────────────────────
def with_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response

@app.after_request
def add_cors(response):
    return with_cors(response)



@app.route("/api", methods=["OPTIONS", "GET"])
def api_docs():
    if request.method == "OPTIONS":
        return Response(status=204)
    return jsonify({
        "name": "Distributed To-Do API",
        "version": "1.0",
        "endpoints": {
            "GET  /api/tasks": "List all tasks",
            "POST /api/tasks": "Create task  {title, description?, priority?, category?}",
            "GET  /api/tasks/<id>": "Get single task",
            "PUT  /api/tasks/<id>": "Update task fields",
            "DELETE /api/tasks/<id>": "Delete task",
            "GET  /api/stats": "Task statistics",
        }
    })



# ─── Task CRUD ───────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET", "OPTIONS"])
def list_tasks():
    if request.method == "OPTIONS":
        return Response(status=204)
    db = SessionLocal()
    try:
        result = db.query(Task).all()
        cat = request.args.get("category")
        pri = request.args.get("priority")
        done = request.args.get("completed")
        if cat:
            result = [t for t in result if t.category.lower() == cat.lower()]
        if pri:
            result = [t for t in result if t.priority == pri]
        if done is not None:
            flag = done.lower() == "true"
            result = [t for t in result if t.completed == flag]
        result.sort(key=lambda t: t.created_at, reverse=True)
        return jsonify([{
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "priority": t.priority,
            "category": t.category,
            "completed": t.completed,
            "created_at": t.created_at.isoformat() + "Z",
            "updated_at": t.updated_at.isoformat() + "Z",
        } for t in result])
    finally:
        db.close()


@app.route("/api/tasks", methods=["POST"])
def create_task():
    body = request.get_json(silent=True) or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title is required"}), 400

    task_id = str(uuid.uuid4())
    now = datetime.utcnow()

    db = SessionLocal()
    try:
        task = Task(
            id=task_id,
            title=title,
            description=body.get("description", ""),
            priority=body.get("priority", "medium"),
            category=body.get("category", "General"),
            created_at=now,
            updated_at=now
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return jsonify({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "category": task.category,
            "completed": task.completed,
            "created_at": task.created_at.isoformat() + "Z",
            "updated_at": task.updated_at.isoformat() + "Z",
        }), 201
    finally:
        db.close()


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return jsonify({"error": "Not found"}), 404
        return jsonify({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "category": task.category,
            "completed": task.completed,
            "created_at": task.created_at.isoformat() + "Z",
            "updated_at": task.updated_at.isoformat() + "Z",
        })
    finally:
        db.close()


@app.route("/api/tasks/<task_id>", methods=["PUT", "OPTIONS"])
def update_task(task_id):
    if request.method == "OPTIONS":
        return Response(status=204)
    body = request.get_json(silent=True) or {}

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return jsonify({"error": "Not found"}), 404

        allowed = {"title", "description", "priority", "category", "completed"}
        for key in allowed:
            if key in body:
                setattr(task, key, body[key])
        task.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(task)

        return jsonify({
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "priority": task.priority,
            "category": task.category,
            "completed": task.completed,
            "created_at": task.created_at.isoformat() + "Z",
            "updated_at": task.updated_at.isoformat() + "Z",
        })
    finally:
        db.close()


@app.route("/api/tasks/<task_id>", methods=["DELETE", "OPTIONS"])
def delete_task(task_id):
    if request.method == "OPTIONS":
        return Response(status=204)

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return jsonify({"error": "Not found"}), 404
        db.delete(task)
        db.commit()
        return jsonify({"deleted": task_id})
    finally:
        db.close()


@app.route("/api/stats")
def stats():
    db = SessionLocal()
    try:
        all_tasks = db.query(Task).all()
        total = len(all_tasks)
        completed = sum(1 for t in all_tasks if t.completed)
        by_priority = {"low": 0, "medium": 0, "high": 0}
        by_category = {}
        for t in all_tasks:
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            by_category[t.category] = by_category.get(t.category, 0) + 1
        return jsonify({
            "total": total,
            "completed": completed,
            "pending": total - completed,
            "by_priority": by_priority,
            "by_category": by_category,
        })
    finally:
        db.close()


# ─── Serve embedded web client ───────────────────────────────────────────────

WEB_CLIENT_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Distributed To-Do List</title>
<style>
  :root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --success: #10b981;
    --danger: #ef4444;
    --warn: #f59e0b;
    --bg: #0f0f1a;
    --surface: #1a1a2e;
    --surface2: #16213e;
    --border: #2d2d5e;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --low: #10b981;
    --medium: #f59e0b;
    --high: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  
  header {
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%);
    border-bottom: 1px solid var(--border);
    padding: 1rem 2rem;
    display: flex; align-items: center; justify-content: space-between;
  }
  .logo { display: flex; align-items: center; gap: 0.75rem; }
  .logo-icon { width: 40px; height: 40px; background: var(--primary); border-radius: 10px;
    display: flex; align-items: center; justify-content: center; font-size: 1.4rem; }
  h1 { font-size: 1.4rem; font-weight: 700; }
  .subtitle { font-size: 0.75rem; color: var(--muted); }
  .status { display: flex; align-items: center; gap: 0.5rem; font-size: 0.85rem; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--danger); transition: background .3s; }
  .dot.connected { background: var(--success); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }

  .container { max-width: 1000px; margin: 0 auto; padding: 2rem 1rem; }
  
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 1rem; margin-bottom: 2rem; }
  .stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1rem; text-align: center; }
  .stat-num { font-size: 2rem; font-weight: 700; color: var(--primary); }
  .stat-label { font-size: 0.75rem; color: var(--muted); margin-top: 0.25rem; }

  .form-card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 1.5rem; margin-bottom: 2rem; }
  .form-card h2 { font-size: 1rem; margin-bottom: 1rem; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; font-size:.75rem; }
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
  .form-grid .full { grid-column: 1/-1; }
  input, textarea, select {
    width: 100%; padding: 0.625rem 0.875rem; border-radius: 8px;
    border: 1px solid var(--border); background: var(--bg);
    color: var(--text); font-size: 0.9rem; font-family: inherit;
    transition: border-color .2s;
  }
  input:focus, textarea:focus, select:focus { outline: none; border-color: var(--primary); }
  textarea { resize: vertical; min-height: 70px; }
  .btn {
    padding: 0.625rem 1.25rem; border-radius: 8px; border: none; cursor: pointer;
    font-size: 0.9rem; font-weight: 600; font-family: inherit; transition: all .2s;
  }
  .btn-primary { background: var(--primary); color: #fff; }
  .btn-primary:hover { background: var(--primary-dark); transform: translateY(-1px); }
  .btn-success { background: var(--success); color: #fff; }
  .btn-danger { background: var(--danger); color: #fff; }
  .btn-ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
  .btn-ghost:hover { border-color: var(--primary); color: var(--primary); }
  .btn-sm { padding: 0.35rem 0.75rem; font-size: 0.8rem; }

  .filters { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.25rem; align-items: center; }
  .filter-btn {
    padding: .375rem .875rem; border-radius: 20px; border: 1px solid var(--border);
    background: transparent; color: var(--muted); cursor: pointer; font-size: .8rem; transition: all .2s;
  }
  .filter-btn.active { background: var(--primary); border-color: var(--primary); color: #fff; }
  .filter-label { font-size: .75rem; color: var(--muted); margin-right: .25rem; }

  .tasks-list { display: flex; flex-direction: column; gap: 0.75rem; }
  .task-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1rem 1.25rem; display: flex; align-items: flex-start; gap: 1rem;
    transition: transform .2s, border-color .2s; animation: slideIn .3s ease;
    position: relative; overflow: hidden;
  }
  .task-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
  }
  .task-card.priority-low::before { background: var(--low); }
  .task-card.priority-medium::before { background: var(--medium); }
  .task-card.priority-high::before { background: var(--high); }
  .task-card:hover { transform: translateY(-2px); border-color: var(--primary); }
  .task-card.completed { opacity: .55; }
  @keyframes slideIn { from{opacity:0;transform:translateY(-10px)} to{opacity:1;transform:translateY(0)} }

  .task-check { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--border);
    cursor: pointer; flex-shrink: 0; margin-top: 2px; display: flex; align-items: center; justify-content: center;
    transition: all .2s; background: transparent; }
  .task-check.checked { background: var(--success); border-color: var(--success); }
  .task-check.checked::after { content: '✓'; color: #fff; font-size: .75rem; font-weight: 700; }

  .task-body { flex: 1; min-width: 0; }
  .task-title { font-weight: 600; font-size: .95rem; }
  .task-title.done { text-decoration: line-through; color: var(--muted); }
  .task-desc { font-size: .82rem; color: var(--muted); margin-top: .25rem; }
  .task-meta { display: flex; gap: .5rem; flex-wrap: wrap; margin-top: .5rem; align-items: center; }
  .badge {
    padding: .15rem .5rem; border-radius: 10px; font-size: .7rem; font-weight: 600;
    background: var(--surface2); border: 1px solid var(--border);
  }
  .badge.low { color: var(--low); border-color: var(--low); }
  .badge.medium { color: var(--medium); border-color: var(--medium); }
  .badge.high { color: var(--high); border-color: var(--high); }
  .task-date { font-size: .7rem; color: var(--muted); }

  .task-actions { display: flex; gap: .5rem; align-items: center; }

  .modal-overlay {
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,.7);
    align-items: center; justify-content: center; z-index: 100;
  }
  .modal-overlay.open { display: flex; }
  .modal {
    background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
    padding: 1.5rem; width: 90%; max-width: 480px; animation: modalIn .25s ease;
  }
  @keyframes modalIn { from{opacity:0;transform:scale(.95)} to{opacity:1;transform:scale(1)} }
  .modal h2 { margin-bottom: 1rem; }
  .modal-footer { display: flex; gap: .5rem; justify-content: flex-end; margin-top: 1.25rem; }
  label { font-size: .8rem; color: var(--muted); display: block; margin-bottom: .3rem; margin-top: .75rem; }

  .toast {
    position: fixed; bottom: 2rem; right: 2rem; background: var(--surface);
    border: 1px solid var(--border); border-radius: 10px; padding: .75rem 1.25rem;
    font-size: .85rem; z-index: 999; animation: toastIn .3s ease;
    box-shadow: 0 8px 32px rgba(0,0,0,.4);
  }
  @keyframes toastIn { from{opacity:0;transform:translateY(20px)} to{opacity:1;transform:translateY(0)} }
  .empty { text-align: center; padding: 3rem; color: var(--muted); }
  .empty-icon { font-size: 3rem; margin-bottom: 1rem; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">✅</div>
    <div>
      <h1>Distributed To-Do List</h1>
      <div class="subtitle">Real-time shared task manager</div>
    </div>
  </div>
  <div class="status">
    <div class="dot" id="statusDot"></div>
    <span id="statusText">Connecting…</span>
  </div>
</header>

<div class="container">
  <!-- Stats -->
  <div class="stats">
    <div class="stat-card"><div class="stat-num" id="statTotal">0</div><div class="stat-label">Total Tasks</div></div>
    <div class="stat-card"><div class="stat-num" id="statPending" style="color:var(--warn)">0</div><div class="stat-label">Pending</div></div>
    <div class="stat-card"><div class="stat-num" id="statDone" style="color:var(--success)">0</div><div class="stat-label">Completed</div></div>
    <div class="stat-card"><div class="stat-num" id="statHigh" style="color:var(--danger)">0</div><div class="stat-label">High Priority</div></div>
  </div>

  <!-- Add Task Form -->
  <div class="form-card">
    <h2>➕ Add New Task</h2>
    <div class="form-grid">
      <input class="full" type="text" id="newTitle" placeholder="Task title *" />
      <textarea class="full" id="newDesc" placeholder="Description (optional)"></textarea>
      <select id="newPriority">
        <option value="low">🟢 Low Priority</option>
        <option value="medium" selected>🟡 Medium Priority</option>
        <option value="high">🔴 High Priority</option>
      </select>
      <input type="text" id="newCategory" placeholder="Category (e.g. Work, Personal)" value="General" />
      <div class="full" style="display:flex;justify-content:flex-end">
        <button class="btn btn-primary" onclick="addTask()">Add Task</button>
      </div>
    </div>
  </div>

  <!-- Filters -->
  <div class="filters">
    <span class="filter-label">Filter:</span>
    <button class="filter-btn active" onclick="setFilter('all',this)">All</button>
    <button class="filter-btn" onclick="setFilter('pending',this)">Pending</button>
    <button class="filter-btn" onclick="setFilter('completed',this)">Completed</button>
    <button class="filter-btn" onclick="setFilter('high',this)">🔴 High</button>
    <button class="filter-btn" onclick="setFilter('medium',this)">🟡 Medium</button>
    <button class="filter-btn" onclick="setFilter('low',this)">🟢 Low</button>
  </div>

  <!-- Task List -->
  <div class="tasks-list" id="tasksList"></div>
</div>

<!-- Edit Modal -->
<div class="modal-overlay" id="editModal">
  <div class="modal">
    <h2>✏️ Edit Task</h2>
    <input type="hidden" id="editId" />
    <label>Title</label>
    <input type="text" id="editTitle" />
    <label>Description</label>
    <textarea id="editDesc"></textarea>
    <label>Priority</label>
    <select id="editPriority">
      <option value="low">🟢 Low</option>
      <option value="medium">🟡 Medium</option>
      <option value="high">🔴 High</option>
    </select>
    <label>Category</label>
    <input type="text" id="editCategory" />
    <div class="modal-footer">
      <button class="btn btn-ghost" onclick="closeEdit()">Cancel</button>
      <button class="btn btn-primary" onclick="saveEdit()">Save Changes</button>
    </div>
  </div>
</div>

<script>
const API = "/api";
let tasks = {};
let currentFilter = "all";

// ── Polling ──────────────────────────────────────────────────────────────────
function pollTasks() {
  fetch(API + "/tasks")
    .then(r => r.json())
    .then(data => {
      tasks = {};
      data.forEach(t => tasks[t.id] = t);
      render();
      updateStats();
      setStatus(true);
    })
    .catch(() => setStatus(false));
}

function startPolling() {
  setStatus(true);
  pollTasks();
  setInterval(pollTasks, 2000);
}

function setStatus(ok) {
  document.getElementById("statusDot").className = "dot" + (ok ? " connected" : "");
  document.getElementById("statusText").textContent = ok ? "Live ✦ Connected" : "Reconnecting…";
}


// ── Render ───────────────────────────────────────────────────────────────────
function filtered() {
  let list = Object.values(tasks);
  if (currentFilter === "pending") list = list.filter(t => !t.completed);
  else if (currentFilter === "completed") list = list.filter(t => t.completed);
  else if (["low","medium","high"].includes(currentFilter)) list = list.filter(t => t.priority === currentFilter);
  return list.sort((a,b) => new Date(b.created_at)-new Date(a.created_at));
}

function render() {
  const list = filtered();
  const el = document.getElementById("tasksList");
  if (list.length === 0) {
    el.innerHTML = '<div class="empty"><div class="empty-icon">📋</div><p>No tasks found</p></div>';
    return;
  }
  el.innerHTML = list.map(t => `
    <div class="task-card priority-${t.priority} ${t.completed ? 'completed' : ''}" id="tc-${t.id}">
      <div class="task-check ${t.completed ? 'checked' : ''}" onclick="toggleDone('${t.id}')"></div>
      <div class="task-body">
        <div class="task-title ${t.completed ? 'done' : ''}">${esc(t.title)}</div>
        ${t.description ? `<div class="task-desc">${esc(t.description)}</div>` : ""}
        <div class="task-meta">
          <span class="badge ${t.priority}">${t.priority}</span>
          <span class="badge">${esc(t.category)}</span>
          <span class="task-date">${fmtDate(t.created_at)}</span>
        </div>
      </div>
      <div class="task-actions">
        <button class="btn btn-ghost btn-sm" onclick="openEdit('${t.id}')">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="delTask('${t.id}')">Delete</button>
      </div>
    </div>
  `).join("");
}

function updateStats() {
  const all = Object.values(tasks);
  document.getElementById("statTotal").textContent = all.length;
  document.getElementById("statPending").textContent = all.filter(t => !t.completed).length;
  document.getElementById("statDone").textContent = all.filter(t => t.completed).length;
  document.getElementById("statHigh").textContent = all.filter(t => t.priority === "high").length;
}

// ── Actions ──────────────────────────────────────────────────────────────────
async function addTask() {
  const title = document.getElementById("newTitle").value.trim();
  if (!title) { toast("⚠️ Please enter a title"); return; }
  const body = { title, description: document.getElementById("newDesc").value,
    priority: document.getElementById("newPriority").value,
    category: document.getElementById("newCategory").value || "General" };
  await fetch(API + "/tasks", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body) });
  document.getElementById("newTitle").value = "";
  document.getElementById("newDesc").value = "";
}

async function toggleDone(id) {
  const t = tasks[id];
  await fetch(API + "/tasks/" + id, { method:"PUT", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({ completed: !t.completed }) });
}

async function delTask(id) {
  if (!confirm("Delete this task?")) return;
  await fetch(API + "/tasks/" + id, { method:"DELETE" });
}

function openEdit(id) {
  const t = tasks[id];
  document.getElementById("editId").value = id;
  document.getElementById("editTitle").value = t.title;
  document.getElementById("editDesc").value = t.description;
  document.getElementById("editPriority").value = t.priority;
  document.getElementById("editCategory").value = t.category;
  document.getElementById("editModal").classList.add("open");
}
function closeEdit() { document.getElementById("editModal").classList.remove("open"); }

async function saveEdit() {
  const id = document.getElementById("editId").value;
  const body = { title: document.getElementById("editTitle").value,
    description: document.getElementById("editDesc").value,
    priority: document.getElementById("editPriority").value,
    category: document.getElementById("editCategory").value };
  await fetch(API + "/tasks/" + id, { method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify(body) });
  closeEdit();
}

function setFilter(f, btn) {
  currentFilter = f;
  document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  render();
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }
function fmtDate(iso) { return new Date(iso).toLocaleDateString(undefined, {month:"short",day:"numeric",hour:"2-digit",minute:"2-digit"}); }

let toastTimer;
function toast(msg) {
  let el = document.getElementById("toast");
  if (!el) { el = document.createElement("div"); el.id="toast"; el.className="toast"; document.body.appendChild(el); }
  el.textContent = msg; el.style.display = "block";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display="none"; }, 3000);
}

// Handle Enter key in title input
document.getElementById("newTitle").addEventListener("keydown", e => { if(e.key==="Enter") addTask(); });
document.getElementById("editModal").addEventListener("click", e => { if(e.target===e.currentTarget) closeEdit(); });

startPolling();

</script>
</body>
</html>"""


@app.route("/")
def index():
    return WEB_CLIENT_HTML


# ─── Seed data ───────────────────────────────────────────────────────────────
def seed():
    db = SessionLocal()
    try:
        if db.query(Task).count() > 0:
            return
        samples = [
            ("Set up project repository", "Initialize Git, create README and folder structure", "high", "Development"),
            ("Design database schema", "Plan tables for users, tasks, and categories", "high", "Development"),
            ("Write unit tests", "Cover all API endpoints with pytest", "medium", "Testing"),
            ("Deploy to production", "Configure server, set env vars, enable HTTPS", "medium", "DevOps"),
            ("Update project documentation", "Add API docs and usage examples", "low", "Documentation"),
        ]
        now = datetime.utcnow()
        for title, desc, pri, cat in samples:
            task = Task(
                id=str(uuid.uuid4()),
                title=title,
                description=desc,
                priority=pri,
                category=cat,
                created_at=now,
                updated_at=now,
            )
            db.add(task)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    print("\n" + "="*55)
    print("  Distributed To-Do Server  🚀")
    print("="*55)
    print("  Web client  → http://localhost:5000")
    print("  REST API    → http://localhost:5000/api/tasks")
    print("="*55 + "\n")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
