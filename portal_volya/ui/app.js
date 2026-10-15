        const authOverlay = document.getElementById('auth-overlay');
        const usernameInput = document.getElementById('username-input');
        const currentPlayerLabel = document.getElementById('current-player-label');
        const threadsDrawer = document.getElementById('threads-drawer');
        const threadsContainer = document.getElementById('threads-container');

        const modalOverlay = document.getElementById('modal-overlay');
        const modalTitleText = document.getElementById('modal-title-text');
        const modalDescText = document.getElementById('modal-desc-text');
        const modalInputField = document.getElementById('modal-input-field');
        const modalConfirmBtn = document.getElementById('modal-confirm-btn');

        const chatSidebar = document.getElementById('chat-sidebar');
        const chatResizer = document.getElementById('chat-resizer');
        const messagesContainer = document.getElementById('chat-messages');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const viewport = document.getElementById('viewport');
        const fileUploadInput = document.getElementById('file-upload-input');
        
        let ws = null;
        let currentThreadId = null;
        let typingMessageElement = null;
        let modalCallback = null;

        // Логика ресайзера ширины чата с сохранением в localStorage
        let isResizing = false;

        // Восстанавливаем сохраненную ширину чата при загрузке
        const savedChatWidth = localStorage.getItem('volya_chat_width');
        if (savedChatWidth) {
            chatSidebar.style.width = savedChatWidth + 'px';
        }

        chatResizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            chatResizer.classList.add('resizing');
            document.body.style.cursor = 'ew-resize';
            e.preventDefault();
        });

        window.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const newWidth = e.clientX;
            if (newWidth >= 300 && newWidth <= window.innerWidth * 0.8) {
                chatSidebar.style.width = newWidth + 'px';
            }
        });

        window.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                chatResizer.classList.remove('resizing');
                document.body.style.cursor = 'default';
                // Сохраняем выбранную ширину в localStorage
                localStorage.setItem('volya_chat_width', chatSidebar.offsetWidth);
            }
        });

        function getCookie(name) {
            const value = `; ${document.cookie}`;
            const parts = value.split(`; ${name}=`);
            if (parts.length === 2) return parts.pop().split(';').shift();
            return null;
        }

        window.addEventListener('DOMContentLoaded', () => {
            loadRegisteredPlayersHint();
            const sessionToken = getCookie('volya_session');
            if (sessionToken) {
                authOverlay.style.display = 'none';
                initWebSocketAndThreads(sessionToken);
            }
        });

        function loadRegisteredPlayersHint() {
            fetch('/api/players')
                .then(res => res.json())
                .then(players => {
                    const hintContainer = document.getElementById('players-hint-container');
                    if (!hintContainer || !players || players.length === 0) return;
                    hintContainer.style.display = 'block';
                    hintContainer.innerHTML = '<div style="margin-bottom: 8px; color: rgba(255,255,255,0.7); font-size: 12px;">Быстрый выбор соратника:</div>' +
                        players.map(p => `<button type="button" class="player-quick-btn" onclick="quickSelectPlayer('${p.username}')">${p.username}</button>`).join('');
                })
                .catch(() => {});
        }

        function quickSelectPlayer(name) {
            usernameInput.value = name;
            submitLogin();
        }

        function logoutPlayer() {
            document.cookie = "volya_session=; path=/; expires=Thu, 01 Jan 1970 00:00:00 UTC;";
            if (ws) {
                try { ws.close(); } catch(e) {}
            }
            location.reload();
        }

        function toggleThreadsDrawer() {
            threadsDrawer.classList.toggle('open');
        }

        function submitLogin() {
            const username = usernameInput.value.trim();
            if (!username) {
                alert('Пожалуйста, введите ваше вольное имя.');
                return;
            }

            fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    authOverlay.style.display = 'none';
                    currentPlayerLabel.innerText = `Игрок: ${data.username}`;
                    initWebSocketAndThreads(data.token);
                } else {
                    alert('Ошибка входа: ' + (data.error || 'Неизвестная ошибка'));
                }
            })
            .catch(err => {
                alert('Сбой запроса авторизации: ' + err.message);
            });
        }

        // Функция обработки загрузки файла
        function handleFileUpload(input) {
            const file = input.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append("file", file);

            appendMessage('user', `Загрузить файл: ${file.name}`);
            showTypingIndicator();
            
            const spanElem = document.getElementById('typing-text-span');
            if (spanElem) spanElem.innerText = `Загрузка файла ${file.name}...`;

            fetch('/api/upload', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                hideTypingIndicator();
                if (data.success) {
                    const successText = `✅ Файл «${data.filename}» успешно загружен.`;
                    appendMessage('assistant', successText);
                    
                    const autoMsg = `Я загрузил файл ${data.filename}.`;
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        showTrustAndSend(autoMsg, false);
                    }
                } else {
                    alert('Ошибка загрузки: ' + (data.error || 'Неизвестная ошибка'));
                }
                input.value = '';
            })
            .catch(err => {
                hideTypingIndicator();
                alert('Сбой загрузки файла: ' + err.message);
                input.value = '';
            });
        }

        function initWebSocketAndThreads(token) {
            loadThreads();

            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws?token=${encodeURIComponent(token)}`);

            ws.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);

                    if (data.type === 'error') {
                        hideTypingIndicator();
                        alert(data.message);
                        authOverlay.style.display = 'flex';
                        return;
                    }

                    if (data.type === 'status_update') {
                        showToolCallIndicator(data.status_text);
                        return;
                    }

                    hideTypingIndicator();

                    if (data.thread_id) {
                        currentThreadId = data.thread_id;
                        highlightActiveThread();
                    }

                    if (data.type === 'reply') {
                        if (data.chat_text) appendMessage('assistant', data.chat_text);
                        renderCanvas(data.canvas_type, data.canvas_content);
                        loadThreads();
                    } 
                    else if (data.type === 'restore') {
                        if (data.username) {
                            currentPlayerLabel.innerText = data.username;
                        }
                        messagesContainer.innerHTML = '';
                        if (data.history) {
                            data.history.forEach(msg => {
                                appendMessage(msg.role, msg.text);
                            });
                        }
                        if (data.canvas_content && data.canvas_content.trim() !== '') {
                            renderCanvas(data.canvas_type, data.canvas_content);
                        } else {
                            viewport.innerHTML = '';
                        }
                        loadThreads();
                    }
                } catch (err) {
                    hideTypingIndicator();
                    console.error("[JSON ПАРСЕР СБОЙ]:", err, event.data);
                }
            };
        }

        let activeTargetQuestId = 1;

        async function loadThreads() {
            try {
                const [questsRes, threadsRes] = await Promise.all([
                    fetch('/api/quests'),
                    fetch('/api/threads')
                ]);

                if (questsRes.status === 401 || threadsRes.status === 401) {
                    authOverlay.style.display = 'flex';
                    return;
                }

                const quests = await questsRes.json();
                const threads = await threadsRes.json();

                // Группируем беседы по quest_id
                const threadsByQuest = {};
                threads.forEach(t => {
                    const qId = t.quest_id || 1;
                    if (!threadsByQuest[qId]) threadsByQuest[qId] = [];
                    threadsByQuest[qId].push(t);
                });

                let html = '';
                if (!quests || quests.length === 0) {
                    html = '<div style="color: rgba(255,255,255,0.5); font-size:12px; text-align:center; padding:20px;">Нет активных квестов для участия</div>';
                } else {
                    quests.forEach(q => {
                        const qThreads = threadsByQuest[q.id] || [];
                        const isChild = q.parent_quest_id ? 'style="margin-left: 12px;"' : '';
                        const qIcon = q.id === 1 ? '🌿' : '🌱';

                        let threadsHtml = '';
                        if (qThreads.length === 0) {
                            threadsHtml = '<div class="quest-empty-threads">Пока нет бесед</div>';
                        } else {
                            qThreads.forEach(t => {
                                const isActive = t.thread_id === currentThreadId ? 'active' : '';
                                threadsHtml += `
                                    <div class="thread-item ${isActive}" onclick="switchThread('${t.thread_id}')">
                                        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-grow: 1;">${t.title}</span>
                                        <button class="thread-del" onclick="event.stopPropagation(); promptDeleteThread('${t.thread_id}', '${t.title.replace(/'/g, "\\'")}')" title="Удалить беседу">×</button>
                                    </div>
                                `;
                            });
                        }

                        html += `
                            <div class="quest-node" ${isChild}>
                                <div class="quest-header">
                                    <div class="quest-title-wrap" title="${q.title}">
                                        <span>${qIcon}</span>
                                        <span>${q.title}</span>
                                    </div>
                                    <button class="quest-add-btn" onclick="event.stopPropagation(); openCreateThreadModal(${q.id}, '${q.title.replace(/'/g, "\\'")}')" title="Создать беседу в квесте «${q.title}»">+</button>
                                </div>
                                <div class="quest-threads">
                                    ${threadsHtml}
                                </div>
                            </div>
                        `;
                    });
                }
                threadsContainer.innerHTML = html;
            } catch (err) {
                console.error("[ОШИБКА ЗАГРУЗКИ ДЕРЕВА КВЕСТОВ]:", err);
            }
        }

        function switchThread(threadId) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'switch_thread', thread_id: threadId }));
                toggleThreadsDrawer();
            }
        }

        function openCreateThreadModal(questId = 1, questTitle = 'Воля') {
            activeTargetQuestId = questId;
            modalTitleText.innerText = "💬 Новая беседа";
            modalDescText.innerText = `Введите название беседы в квесте «${questTitle}»:`;
            modalInputField.style.display = "block";
            modalConfirmBtn.innerText = "Создать";
            modalConfirmBtn.className = "modal-btn confirm";
            
            const defaultTitle = 'Беседа ' + new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            modalInputField.value = defaultTitle;
            
            modalCallback = () => {
                const title = modalInputField.value.trim() || 'Беседа воли';
                closeCustomModal();
                fetch('/api/threads', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title, quest_id: activeTargetQuestId })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        switchThread(data.thread_id);
                    }
                });
            };

            modalOverlay.style.display = 'flex';
            modalInputField.focus();
            modalInputField.select();
        }

        function promptDeleteThread(threadId, threadTitle) {
            modalTitleText.innerText = "🗑️ Удаление беседы";
            modalDescText.innerText = `Удалить беседу «${threadTitle}» и всю её историю из Живого Древа?`;
            modalInputField.style.display = "none";
            modalConfirmBtn.innerText = "Удалить";
            modalConfirmBtn.className = "modal-btn confirm danger";

            modalCallback = () => {
                closeCustomModal();
                fetch(`/api/threads/${threadId}`, { method: 'DELETE' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            loadThreads();
                            window.location.reload();
                        }
                    });
            };

            modalOverlay.style.display = 'flex';
            modalConfirmBtn.focus();
        }

        function closeCustomModal() {
            modalOverlay.style.display = 'none';
            modalCallback = null;
        }

        function confirmCustomModal() {
            if (modalCallback) {
                modalCallback();
            }
        }

        modalInputField.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                confirmCustomModal();
            } else if (e.key === 'Escape') {
                closeCustomModal();
            }
        });

        window.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modalOverlay.style.display === 'flex') {
                closeCustomModal();
            }
        });

        function highlightActiveThread() {
            loadThreads();
        }

        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });

        function insertEmoji(emoji) {
            const start = messageInput.selectionStart;
            const end = messageInput.selectionEnd;
            const text = messageInput.value;
            messageInput.value = text.substring(0, start) + emoji + text.substring(end);
            messageInput.selectionStart = messageInput.selectionEnd = start + emoji.length;
            messageInput.focus();
            messageInput.style.height = 'auto';
            messageInput.style.height = (messageInput.scrollHeight) + 'px';
        }

        function appendMessage(role, text) {
            const msgDiv = document.createElement('div');
            msgDiv.classList.add('message', role);
            msgDiv.innerText = text;
            messagesContainer.appendChild(msgDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        function showTypingIndicator() {
            if (typingMessageElement) return;
            typingMessageElement = document.createElement('div');
            typingMessageElement.classList.add('message', 'typing');
            typingMessageElement.innerHTML = `<span id="typing-text-span">Эйра думает</span><div class="typing-dots"><span></span><span></span><span></span></div>`;
            messagesContainer.appendChild(typingMessageElement);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            messageInput.disabled = true;
            sendBtn.disabled = true;
        }

        function showToolCallIndicator(statusText) {
            if (!typingMessageElement) {
                showTypingIndicator();
            }
            const spanElem = document.getElementById('typing-text-span');
            if (spanElem) {
                spanElem.innerText = statusText;
            }
            
            setTimeout(() => {
                const currentSpan = document.getElementById('typing-text-span');
                if (currentSpan && currentSpan.innerText === statusText) {
                    currentSpan.innerText = "Эйра думает";
                }
            }, 2500);
        }

        function hideTypingIndicator() {
            if (typingMessageElement) {
                typingMessageElement.remove();
                typingMessageElement = null;
            }
            messageInput.disabled = false;
            sendBtn.disabled = false;
            messageInput.focus();
        }

        function renderCanvas(canvasType, canvasContent) {
            if (!canvasContent || canvasContent.trim() === "") return;

            if (canvasType === "load_tmp") {
                const fileName = canvasContent.substring(9).trim();
                fetch(`/tmp/${fileName}?t=${Date.now()}`)
                    .then(res => {
                        if (!res.ok) throw new Error(`Статус: ${res.status}`);
                        return res.text();
                    })
                    .then(fileContent => buildGlassWindow(`Инспекция файла: ${fileName}`, fileContent, true))
                    .catch(err => {
                        viewport.innerHTML = `<div style="padding:20px; color:#ef4444;">Ошибка загрузки файла: ${err.message}</div>`;
                    });
            } else if (canvasType === "html") {
                buildGlassWindow("Холст", canvasContent, true);
            } else if (canvasType === "text") {
                buildGlassWindow("Инспекция", canvasContent, false);
            } else {
                try {
                    const runScript = new Function(canvasContent);
                    runScript();
                } catch (err) {
                    buildGlassWindow("Вывод", canvasContent, false);
                }
            }
        }

        function buildGlassWindow(titleText, contentText, isHtml = false) {
            viewport.innerHTML = '';
            
            const windowDiv = document.createElement('div');
            windowDiv.className = 'glass-window';
            
            const titleH2 = document.createElement('div');
            titleH2.className = 'glass-title';
            titleH2.innerText = titleText;
            
            const boxDiv = document.createElement('div');
            boxDiv.className = 'glass-content-box';
            
            if (isHtml) {
                boxDiv.innerHTML = contentText;
            } else {
                const preElement = document.createElement('pre');
                preElement.className = 'code-view';
                preElement.textContent = contentText;
                boxDiv.appendChild(preElement);
            }
            
            windowDiv.appendChild(titleH2);
            windowDiv.appendChild(boxDiv);
            viewport.appendChild(windowDiv);
        }

        function sendMessage() {
            const text = messageInput.value.trim();
            if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
            
            appendMessage('user', text);
            showTrustAndSend(text, true);
        }

        function showTrustAndSend(text, shouldAppend = true) {
            showTypingIndicator();
            ws.send(JSON.stringify({ chat_text: text }));
            messageInput.value = '';
            messageInput.style.height = 'auto';
        }

        sendBtn.addEventListener('click', sendMessage);
        
        messageInput.addEventListener('keydown', function(e) {
            e.stopPropagation();
            if (e.key === 'Enter') {
                if (e.shiftKey) {
                    return;
                } else {
                    e.preventDefault();
                    sendMessage();
                }
            }
        });
    </script>
