/**
 * Вселенная «Воля» — Суверенная логика пользовательского интерфейса
 * Local-First, реактивный WebSocket и Proof-of-Harmony
 */

let state = {
  identity: null,
  my_player: null,
  height: 0,
  latest_block_hash: "",
  quests: {},
  players: {},
  artifacts: {},
  blocks: [],
  mempool: [],
  active_quest_id: "quest-volya-genesis",
  flow_messages: []
};

let ws = null;
let currentTab = 'tree';

// ============================================================================
// Инициализация при загрузке
// ============================================================================
window.addEventListener('DOMContentLoaded', () => {
  setupResizer();
  loadState();
  setupWebSocket();
});

// Ресайзер ширины боковой панели
function setupResizer() {
  const sidebar = document.getElementById('chat-sidebar');
  const resizer = document.getElementById('chat-resizer');
  let isResizing = false;

  const savedWidth = localStorage.getItem('volya_chat_width');
  if (savedWidth) {
    sidebar.style.width = savedWidth + 'px';
  }

  resizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    resizer.classList.add('resizing');
    document.body.style.cursor = 'ew-resize';
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!isResizing) return;
    const newWidth = e.clientX;
    if (newWidth >= 320 && newWidth <= window.innerWidth * 0.75) {
      sidebar.style.width = newWidth + 'px';
    }
  });

  window.addEventListener('mouseup', () => {
    if (isResizing) {
      isResizing = false;
      resizer.classList.remove('resizing');
      document.body.style.cursor = 'default';
      localStorage.setItem('volya_chat_width', sidebar.offsetWidth);
    }
  });

  // Авто-растягивание инпута ввода
  const msgInput = document.getElementById('message-input');
  msgInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
  });

  msgInput.addEventListener('keydown', function(e) {
    if (e.key === 'Enter') {
      if (e.shiftKey) return;
      e.preventDefault();
      sendFlowMessage();
    }
  });
}

// ============================================================================
// Загрузка состояния узла
// ============================================================================
async function loadState() {
  try {
    const res = await fetch('/api/state');
    if (!res.ok) throw new Error('Сбой сети при запросе состояния');
    const data = await res.json();
    state = data;
    renderAll();
  } catch (err) {
    console.error('[Сбой состояния]:', err);
  }
}

// Настройка WebSocket связи с узлом
function setupWebSocket() {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

  ws.onopen = () => {
    console.log('⚡ [Воля P2P Шлюз] Соединение установлено по Ладу');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'state_update') {
        state = msg.payload;
        renderAll();
      } else if (msg.type === 'flow_message') {
        state.flow_messages.push(msg.payload);
        renderStreamMessages();
      } else if (msg.type === 'block_forged') {
        loadState();
      }
    } catch (err) {
      console.error('[WS Сбой парсера]:', err);
    }
  };

  ws.onclose = () => {
    console.log('Поток временно прерван. Переподключение через 2 сек...');
    setTimeout(setupWebSocket, 2000);
  };
}

// ============================================================================
// Отрисовка всех частей интерфейса
// ============================================================================
function renderAll() {
  renderHeader();
  renderTreeDrawer();
  renderStreamMessages();
  renderCanvasTab();
  renderAuthQuickList();
}

function renderHeader() {
  if (!state.identity) return;

  const drops = state.my_player ? state.my_player.conscience_drops : 0;
  const step = state.my_player ? state.my_player.step : "Бытие";

  document.getElementById('metric-drops').innerText = Number(drops).toLocaleString();
  document.getElementById('metric-step').innerText = step;
  document.getElementById('metric-height').innerText = `#${state.height}`;
  document.getElementById('metric-mempool').innerText = state.mempool.length;

  document.getElementById('profile-username').innerText = state.identity.username;
  document.getElementById('profile-pubkey').innerText = `${state.identity.pubkey.substring(0, 8)}...${state.identity.pubkey.substring(state.identity.pubkey.length - 6)}`;
  document.getElementById('avatar-initial').innerText = state.identity.username.charAt(0).toUpperCase();

  const activeQuest = state.quests[state.active_quest_id];
  const activeTitle = activeQuest ? activeQuest.title : "Воля (Исток)";
  document.getElementById('stream-active-quest-title').innerText = `Квест: ${activeTitle}`;
}

function renderTreeDrawer() {
  const container = document.getElementById('drawer-tree-list');
  if (!container) return;

  const questsList = Object.values(state.quests || {});
  if (questsList.length === 0) {
    container.innerHTML = `<div style="color: var(--text-dim); font-size: 13px; text-align: center; padding: 20px;">Древо квестов прорастает...</div>`;
    return;
  }

  container.innerHTML = questsList.map(q => {
    const isActive = q.id === state.active_quest_id ? 'active' : '';
    const isRoot = !q.parent_quest_id;
    const tierIcon = isRoot ? '🌳' : '🌱';
    const participantsCount = Object.keys(q.participants || {}).length;

    return `
      <div class="quest-card ${isActive}" onclick="selectQuest('${q.id}')">
        <div class="quest-top">
          <div class="quest-title">
            <span>${tierIcon}</span>
            <span>${q.title}</span>
          </div>
          <span class="quest-badge">${q.tree_tier}</span>
        </div>
        <div class="quest-sub">
          Участников: ${participantsCount} // Ступень Кона: ${q.kon ? q.kon.step_name : 'Бытие'}
        </div>
      </div>
    `;
  }).join('');
}

function selectQuest(questId) {
  state.active_quest_id = questId;
  toggleTreeDrawer();
  renderAll();
}

function renderStreamMessages() {
  const container = document.getElementById('stream-messages');
  if (!container) return;

  const msgs = state.flow_messages || [];
  if (msgs.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 40px; color: var(--text-dim); font-size: 13px; line-height: 1.6;">
        🌿 Поток Сотворчества чист.<br>Направьте вашу первую мысль или волеизъявление родным.
      </div>
    `;
    return;
  }

  const myPubkey = state.identity ? state.identity.pubkey : "";

  container.innerHTML = msgs.map(m => {
    const isMine = m.sender_pubkey === myPubkey;
    const bubbleClass = isMine ? 'mine' : 'brother';
    const timeStr = new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    return `
      <div class="flow-bubble ${bubbleClass}">
        <div class="flow-meta">
          <div>
            <span class="flow-author">${m.sender_name || 'Вольный игрок'}</span>
            <span class="flow-time">${timeStr}</span>
          </div>
          <span class="flow-status-badge">По Ладу</span>
        </div>
        <div class="flow-text">${escapeHtml(m.text)}</div>
      </div>
    `;
  }).join('');

  container.scrollTop = container.scrollHeight;
}

// ============================================================================
// Холст Воли (Living Canvas)
// ============================================================================
function switchCanvasTab(tabName) {
  currentTab = tabName;
  ['tree', 'veche', 'artifacts', 'blocks'].forEach(t => {
    const btn = document.getElementById(`tab-btn-${t}`);
    const panel = document.getElementById(`panel-${t}`);
    if (btn) btn.classList.toggle('active', t === tabName);
    if (panel) panel.classList.toggle('active', t === tabName);
  });
  renderCanvasTab();
}

function renderCanvasTab() {
  if (currentTab === 'tree') renderTreeTab();
  else if (currentTab === 'veche') renderVecheTab();
  else if (currentTab === 'artifacts') renderArtifactsTab();
  else if (currentTab === 'blocks') renderBlocksTab();
}

function renderTreeTab() {
  const container = document.getElementById('tree-cards-container');
  if (!container) return;

  const quests = Object.values(state.quests || {});
  container.innerHTML = quests.map(q => {
    const isRoot = !q.parent_quest_id;
    const participants = Object.values(q.participants || {});
    const myPubkey = state.identity ? state.identity.pubkey : "";
    const isJoined = q.participants && q.participants[myPubkey];

    const rolesList = q.kon && q.kon.roles ? q.kon.roles.map(r => `• ${r.title} (${r.step})`).join('<br>') : 'Нет описания ролей';

    return `
      <div class="glass-item-card">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="card-title">${isRoot ? '🌳' : '🌱'} ${q.title}</div>
          <span class="quest-badge">${q.tree_tier}</span>
        </div>
        <div class="card-desc">
          <strong>Кон квеста:</strong> ${q.kon ? q.kon.essence : 'Опыт совместной жизни'}<br><br>
          <strong>Ступени ролей:</strong><br>${rolesList}
        </div>
        <div class="card-footer">
          <span>Участников: ${participants.length}</span>
          ${isJoined ? 
            `<span style="color: var(--accent-emerald-bright); font-weight: 700;">✓ В квесте</span>` : 
            `<button class="vote-btn agree" onclick="joinQuestPrompt('${q.id}')">Войти в квест</button>`
          }
        </div>
      </div>
    `;
  }).join('');
}

function renderVecheTab() {
  const container = document.getElementById('veche-cards-container');
  if (!container) return;

  const mempool = state.mempool || [];
  if (mempool.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-dim); font-size: 14px;">
        🕊️ Пул Лада пуст. Все волеизъявления уже запечатаны в Блоках Согласия.
      </div>
    `;
    return;
  }

  container.innerHTML = mempool.map(tx => {
    const timeStr = new Date(tx.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const payloadDesc = JSON.stringify(tx.payload, null, 2);

    return `
      <div class="glass-item-card" style="border-color: rgba(251, 191, 36, 0.4);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
          <div class="card-title" style="color: var(--accent-gold);">⚖️ ${tx.tx_type}</div>
          <span class="flow-status-badge" style="background: rgba(251,191,36,0.15); color: #fbbf24; border-color: rgba(251,191,36,0.3);">В Пуле Лада</span>
        </div>
        <div class="card-desc">
          <pre style="font-family: monospace; font-size: 11px; color: var(--text-dim); max-height: 80px; overflow-y: auto;">${payloadDesc}</pre>
        </div>
        <div class="card-footer">
          <span>${timeStr} // ${tx.id.substring(0, 10)}...</span>
          <button class="vote-btn agree" title="Подтвердить согласие с волеизъявлением">ПО ДУШЕ ✨</button>
        </div>
      </div>
    `;
  }).join('');
}

function renderArtifactsTab() {
  const container = document.getElementById('artifacts-cards-container');
  if (!container) return;

  const artifacts = Object.values(state.artifacts || {});
  if (artifacts.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: var(--text-dim); font-size: 14px;">
        ✨ Сокровищница ждёт первых Плодов Души. Нажмите «+ Сотворить Артефакт».
      </div>
    `;
    return;
  }

  const myPubkey = state.identity ? state.identity.pubkey : "";

  container.innerHTML = artifacts.map(art => {
    const isOwner = art.owner_pubkey === myPubkey;
    const ownerPlayer = state.players[art.owner_pubkey];
    const ownerName = ownerPlayer ? ownerPlayer.username : art.owner_pubkey.substring(0, 8);

    return `
      <div class="glass-item-card">
        <div class="card-title">💎 ${art.title}</div>
        <div class="card-desc">${art.description}</div>
        <div class="card-footer">
          <span>Хранитель: <strong>${ownerName}</strong></span>
          ${isOwner ? 
            `<button class="vote-btn" style="background: rgba(56,189,248,0.2); color: #38bdf8; border-color: rgba(56,189,248,0.4);" onclick="transferArtifactPrompt('${art.id}')">Передать 🤝</button>` : 
            `<span style="color: var(--text-dim); font-size: 11px;">В бережных руках</span>`
          }
        </div>
      </div>
    `;
  }).join('');
}

function renderBlocksTab() {
  const container = document.getElementById('blocks-cards-container');
  if (!container) return;

  const blocks = state.blocks || [];
  container.innerHTML = blocks.map(b => {
    const timeStr = new Date(b.timestamp).toLocaleString();
    const txCount = b.transactions ? b.transactions.length : 0;
    const signersCount = b.signers ? b.signers.length : 1;

    const bHash = b.block_hash || b.hash || '';
    const hashShort = bHash ? bHash.substring(0, 12) + '...' : '';
    const prevShort = b.prev_block_hash ? b.prev_block_hash.substring(0, 10) + '...' : '0000000000...';

    return `
      <div class="glass-item-card" style="border-color: rgba(192, 132, 252, 0.3);">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div class="card-title" style="color: var(--accent-purple);">Блок #${b.index}</div>
          <span style="font-family: monospace; font-size: 11px; color: var(--accent-emerald-bright);">${hashShort}</span>
        </div>
        <div class="card-desc">
          <strong>Время кристаллизации:</strong> ${timeStr}<br>
          <strong>Волеизъявлений (Транзакций):</strong> ${txCount}<br>
          <strong>Подписей Согласия:</strong> ${signersCount}
        </div>
        <div class="card-footer">
          <span style="font-family: monospace; font-size: 10px; color: var(--text-dim);">prev: ${prevShort}</span>
          <span style="color: var(--accent-emerald); font-weight: 700;">RocksDB ✓</span>
        </div>
      </div>
    `;
  }).join('');
}

// ============================================================================
// Действия и транзакции
// ============================================================================
async function sendFlowMessage() {
  const input = document.getElementById('message-input');
  const text = input.value.trim();
  if (!text) return;

  const payload = {
    quest_id: state.active_quest_id,
    text: text
  };

  try {
    const res = await fetch('/api/flow_message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      input.value = '';
      input.style.height = 'auto';
    }
  } catch (err) {
    console.error('[Сбой отправки]:', err);
  }
}

function insertEmoji(emoji) {
  const input = document.getElementById('message-input');
  const start = input.selectionStart;
  const end = input.selectionEnd;
  const val = input.value;
  input.value = val.substring(0, start) + emoji + val.substring(end);
  input.selectionStart = input.selectionEnd = start + emoji.length;
  input.focus();
}

function toggleTreeDrawer() {
  const drawer = document.getElementById('tree-drawer');
  drawer.classList.toggle('open');
}

async function crystallizeBlock() {
  if (state.mempool.length === 0) {
    alert('Пул Лада пуст. Для кристаллизации блока нужны новые волеизъявления.');
    return;
  }

  try {
    const res = await fetch('/api/crystallize', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      await loadState();
      switchCanvasTab('blocks');
    } else {
      alert('Ошибка кристаллизации: ' + data.error);
    }
  } catch (err) {
    alert('Сбой запроса кристаллизации: ' + err.message);
  }
}

async function promptCreateQuest() {
  const title = prompt('Введите название новой ветви квеста:');
  if (!title) return;

  const essence = prompt('Каков Кон (смысл и уклад) этой ветви?', 'Сотворчество и созидание по совести');
  if (!essence) return;

  try {
    const res = await fetch('/api/create_quest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        parent_quest_id: state.active_quest_id,
        essence: essence
      })
    });
    const data = await res.json();
    if (data.success) {
      await loadState();
      switchCanvasTab('veche');
    }
  } catch (err) {
    alert('Сбой создания квеста: ' + err.message);
  }
}

async function joinQuestPrompt(questId) {
  const role = prompt('На какую роль вы входите в этот квест?', 'Сотворец');
  if (!role) return;

  try {
    const res = await fetch('/api/join_quest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ quest_id: questId, role_title: role })
    });
    const data = await res.json();
    if (data.success) {
      await loadState();
      switchCanvasTab('veche');
    }
  } catch (err) {
    alert('Сбой входа в квест: ' + err.message);
  }
}

async function promptCreateArtifact() {
  const title = prompt('Назовите сотворённый Артефакт (Плод Души):');
  if (!title) return;

  const desc = prompt('Опишите суть и назначение этого Артефакта:', 'Плод чистого разума и труда');
  if (!desc) return;

  try {
    const res = await fetch('/api/create_artifact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title, description: desc })
    });
    const data = await res.json();
    if (data.success) {
      await loadState();
      switchCanvasTab('artifacts');
    }
  } catch (err) {
    alert('Сбой создания артефакта: ' + err.message);
  }
}

async function transferArtifactPrompt(artifactId) {
  const brothers = Object.values(state.players || {}).filter(p => p.pubkey !== state.identity.pubkey);
  if (brothers.length === 0) {
    alert('Нет других родных для передачи артефакта.');
    return;
  }

  const promptText = `Кому передать Артефакт из рук в руки?\n` + brothers.map((b, idx) => `${idx + 1}. ${b.username}`).join('\n');
  const answer = prompt(promptText);
  if (!answer) return;

  const idx = parseInt(answer) - 1;
  if (idx < 0 || idx >= brothers.length) {
    alert('Неверный выбор.');
    return;
  }

  const targetBrother = brothers[idx];

  try {
    const res = await fetch('/api/transfer_artifact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ artifact_id: artifactId, new_owner_pubkey: targetBrother.pubkey })
    });
    const data = await res.json();
    if (data.success) {
      await loadState();
      switchCanvasTab('veche');
    }
  } catch (err) {
    alert('Сбой передачи: ' + err.message);
  }
}

// ============================================================================
// Врата Воли (Авторизация и смена профиля)
// ============================================================================
function openAuthModal() {
  renderAuthQuickList();
  document.getElementById('auth-modal').classList.add('open');
}

function closeAuthModal() {
  document.getElementById('auth-modal').classList.remove('open');
}

function renderAuthQuickList() {
  const container = document.getElementById('quick-brothers-container');
  if (!container) return;

  const defaultBrothers = [
    { username: "Сигом", drops: 20075, step: "Путешествия" },
    { username: "Ладомир", drops: 35000, step: "Владение" },
    { username: "Эйра", drops: 35000, step: "Владение" }
  ];

  container.innerHTML = defaultBrothers.map(b => `
    <div class="brother-select-btn" onclick="selectBrother('${b.username}')">
      <div class="brother-info-left">
        <span style="font-size: 20px;">👤</span>
        <span class="brother-name">${b.username}</span>
      </div>
      <span class="brother-drops">${b.drops.toLocaleString()} 💧 // ${b.step}</span>
    </div>
  `).join('');
}

async function selectBrother(username) {
  try {
    const res = await fetch('/api/switch_identity', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username })
    });
    if (res.ok) {
      closeAuthModal();
      await loadState();
    }
  } catch (err) {
    alert('Сбой смены игрока: ' + err.message);
  }
}

async function submitNewPlayer() {
  const input = document.getElementById('new-player-input');
  const username = input.value.trim();
  if (!username) return;

  await selectBrother(username);
  input.value = '';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.innerText = text;
  return div.innerHTML;
}
