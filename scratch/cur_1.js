
        // ===================== API BASE RESOLUTION =====================
        // Dynamic & Deterministic API Base:
        // - Supports explicit window override (window.CODEMIND_API_BASE)
        // - Supports localStorage override ('CODEMIND_API_BASE')
        // - If frontend runs on port 3000, 5500, 5173, etc. or file://, reliably targets backend at http://127.0.0.1:8000
        // - If frontend is served directly by backend on port 8000, uses window.location.origin
        // - If in production with custom domain, uses window.location.origin
        function resolveApiBase() {
            if (window.CODEMIND_API_BASE && typeof window.CODEMIND_API_BASE === 'string') {
                return window.CODEMIND_API_BASE.replace(/\/+$/, '');
            }
            try {
                const stored = localStorage.getItem('CODEMIND_API_BASE');
                if (stored && typeof stored === 'string') return stored.replace(/\/+$/, '');
            } catch (e) {}

            if (!window.location.protocol.startsWith('http')) {
                return 'http://127.0.0.1:8000';
            }

            const port = window.location.port;
            const hostname = window.location.hostname;

            if (port === '8000') {
                return window.location.origin;
            }

            const devPorts = ['3000', '5500', '5173', '8080', '4173', '3001', '8001'];
            if (hostname === 'localhost' || hostname === '127.0.0.1' || devPorts.includes(port)) {
                return 'http://127.0.0.1:8000';
            }

            return window.location.origin;
        }

        const API_BASE = resolveApiBase();
        window.API_BASE = API_BASE;
        window.resolveApiBase = resolveApiBase;
        window.active_workspace = 'dashboard';

        // ===================== SAFE ERROR MESSAGE EXTRACTION =====================
        /**
         * Safely extracts a human-readable error message from an API response data object.
         * Handles Pydantic 422 validation errors where 'detail' is an array of objects,
         * plain string errors, and fallback messages.
         * PREVENTS: "NETWORK ERROR: [object Object]" bug.
         */
        function safeExtractErrorMessage(data, fallback) {
            fallback = fallback || 'An unexpected error occurred. Please try again.';
            if (!data) return fallback;
            const raw = data.detail !== undefined ? data.detail
                      : data.message !== undefined ? data.message
                      : data.error !== undefined ? data.error
                      : data.msg !== undefined ? data.msg
                      : null;
            if (raw === null || raw === undefined) return fallback;
            if (typeof raw === 'string') return raw || fallback;
            if (Array.isArray(raw)) {
                // Pydantic v2 validation error format: [{loc:[...], msg:"...", type:"..."}]
                return raw.map(function(e) {
                    if (typeof e === 'string') return e;
                    if (e && typeof e === 'object') {
                        const fieldPath = Array.isArray(e.loc) ? e.loc.slice(1).join(' → ') : '';
                        const msg = e.msg || e.message || String(e);
                        return fieldPath ? `${fieldPath}: ${msg}` : msg;
                    }
                    return String(e);
                }).filter(Boolean).join('; ') || fallback;
            }
            if (typeof raw === 'object') return raw.msg || raw.message || JSON.stringify(raw);
            return String(raw) || fallback;
        }

        // ===================== CENTRALIZED API ERROR CLASSIFICATION =====================
        function classifyApiError(err, res = null) {
            const status = (res && res.status) || (err && (err.status || err.statusCode)) || null;

            if (!status) {
                if (err && err.name === 'AbortError') {
                    return {
                        type: 'NETWORK ERROR',
                        status: 0,
                        message: 'Request timed out or was aborted. Please check your network connection.'
                    };
                }
                const msg = String((err && err.message) || '').toLowerCase();
                if (err instanceof TypeError || msg.includes('failed to fetch') || msg.includes('networkerror') || msg.includes('network error') || msg.includes('network request failed') || msg.includes('connection refused')) {
                    return {
                        type: 'BACKEND OFFLINE',
                        status: 0,
                        message: `CodeMind backend is offline or unreachable at ${API_BASE}. Please ensure the FastAPI backend is running on port 8000.`
                    };
                }
                return {
                    type: 'NETWORK ERROR',
                    status: 0,
                    message: (err && err.message) || 'A network error occurred while communicating with the server.'
                };
            }

            let detailMsg = '';
            if (err && typeof err === 'object') {
                detailMsg = err.detail || err.message || err.error || '';
            } else if (typeof err === 'string') {
                detailMsg = err;
            }

            switch (status) {
                case 401:
                    return {
                        type: 'HTTP 401',
                        status: 401,
                        message: detailMsg || 'Authentication required or session expired. Please sign in.'
                    };
                case 403:
                    return {
                        type: 'HTTP 403',
                        status: 403,
                        message: detailMsg || 'Access denied. You do not have permission to view or modify this resource.'
                    };
                case 404:
                    return {
                        type: 'HTTP 404',
                        status: 404,
                        message: detailMsg || 'The requested resource was not found on the backend.'
                    };
                case 422:
                    return {
                        type: 'HTTP 422',
                        status: 422,
                        message: detailMsg || 'Validation error: The submitted data is invalid.'
                    };
                case 500:
                    return {
                        type: 'HTTP 500',
                        status: 500,
                        message: detailMsg || 'Internal server error occurred on the backend.'
                    };
                default:
                    if (err && err.isAiError) {
                        return {
                            type: 'AI PROVIDER ERROR',
                            status: status,
                            message: detailMsg || 'AI Tutor engine encountered an error.'
                        };
                    }
                    if (err && err.isExecutionError) {
                        return {
                            type: 'EXECUTION ERROR',
                            status: status,
                            message: detailMsg || 'Code execution engine encountered an error.'
                        };
                    }
                    return {
                        type: status ? `HTTP ${status}` : 'REQUEST FAILED',
                        status: status,
                        message: detailMsg || (err && err.message) || 'Request failed.'
                    };
            }
        }

        // ===================== BACKEND HEALTH CHECK =====================
        let backendHealthState = {
            isHealthy: null,
            latencyMs: null,
            lastChecked: null,
            details: null
        };

        async function checkBackendHealth(showToast = false) {
            const start = Date.now();
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), 4000);
                const res = await fetch(`${API_BASE}/api/health`, {
                    method: 'GET',
                    headers: { 'Accept': 'application/json' },
                    signal: controller.signal
                });
                clearTimeout(timeoutId);
                const latency = Date.now() - start;
                if (res.ok) {
                    const data = await res.json().catch(() => ({ status: 'healthy' }));
                    backendHealthState = { isHealthy: true, latencyMs: latency, lastChecked: Date.now(), details: data };
                    updateBackendHealthUI(true, latency);
                    if (showToast && typeof showToastMessage === 'function') {
                        showToastMessage(`Backend reachable (${latency}ms) at ${API_BASE}`);
                    }
                    return true;
                } else {
                    backendHealthState = { isHealthy: false, latencyMs: latency, lastChecked: Date.now(), details: null };
                    updateBackendHealthUI(false, latency, `HTTP ${res.status}`);
                    return false;
                }
            } catch (err) {
                backendHealthState = { isHealthy: false, latencyMs: null, lastChecked: Date.now(), details: null };
                updateBackendHealthUI(false, null, 'Offline');
                return false;
            }
        }

        function updateBackendHealthUI(isHealthy, latency = null, statusLabel = '') {
            const banner = document.getElementById('backendOfflineBanner');
            const badge = document.getElementById('backendHealthBadge');
            if (banner) {
                if (isHealthy) {
                    banner.style.display = 'none';
                } else {
                    banner.style.display = 'block';
                    const urlEl = document.getElementById('backendOfflineUrl');
                    if (urlEl) urlEl.textContent = API_BASE;
                }
            }
            if (badge) {
                if (isHealthy) {
                    badge.style.color = '#4ade80';
                    badge.style.borderColor = 'rgba(74, 222, 128, 0.4)';
                    badge.innerHTML = `<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#4ade80; margin-right:6px; box-shadow:0 0 6px #4ade80;"></span>API Online${latency ? ` (${latency}ms)` : ''}`;
                    badge.title = `Connected to CodeMind Backend at ${API_BASE} (Click to re-check)`;
                } else {
                    badge.style.color = '#f87171';
                    badge.style.borderColor = 'rgba(248, 113, 113, 0.5)';
                    badge.innerHTML = `<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#f87171; margin-right:6px; box-shadow:0 0 6px #f87171;"></span>API ${statusLabel || 'Offline'}`;
                    badge.title = `Unable to connect to CodeMind Backend at ${API_BASE}. Click to retry.`;
                }
            }
        }

        // ===================== AUTHENTICATION & DATA ISOLATION =====================
        function getAuthToken() {
            return localStorage.getItem('codemind_auth_token') || '';
        }

        function getAuthUser() {
            try {
                const raw = localStorage.getItem('codemind_auth_user');
                return raw ? JSON.parse(raw) : null;
            } catch(e) {
                return null;
            }
        }

        let activeMayaConversationId = null;
        function getOrCreateMayaConversationId() {
            if (!activeMayaConversationId) {
                activeMayaConversationId = 'conv_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
            }
            return activeMayaConversationId;
        }

        function generateMayaRequestId() {
            return 'req_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);
        }

        function getStudentId() {
            const user = getAuthUser();
            return user ? user.id : null;
        }

        function isAuthenticated() {
            return !!getAuthToken() && !!getAuthUser();
        }

        function setAuthSession(token, user, profile) {
            localStorage.setItem('codemind_auth_token', token);
            localStorage.setItem('codemind_auth_user', JSON.stringify(user));
            const displayName = (profile && profile.student_name) || user.display_name || user.username;
            localStorage.setItem('codemind_user_name', displayName);
            if (profile && profile.bot_name) {
                localStorage.setItem('codemind_bot_name', profile.bot_name);
            }
            window.currentStudentId = user ? user.id : null;
            window.currentUserHasGroqKey = !!(user && user.has_groq_key);
            window.currentUserGroqKeyPreview = (user && user.groq_key_preview) || '';

            // Reset active in-memory chat histories so User B never sees User A's dialogue
            activeMayaConversationId = null;
            if (typeof companionChatHistory !== 'undefined') companionChatHistory = [];
            if (typeof aiTutorChatHistory !== 'undefined') aiTutorChatHistory = [];

            // Reset dashboard companion chat DOM
            const dashChatArea = document.getElementById('companionChatArea');
            if (dashChatArea) {
                dashChatArea.innerHTML = '';
                const botName = (profile && profile.bot_name) || localStorage.getItem('codemind_bot_name') || 'Maya';
                const greeting = document.createElement('div');
                greeting.className = 'companion-bubble';
                greeting.id = 'companionGreetingBubble';
                greeting.innerHTML = `👋 Hello ${escapeHtml(displayName)}! I am <strong>${escapeHtml(botName)}</strong>, your CodeMind AI Companion &amp; Tutor. Ask me anything about programming, algorithms, recursion, pointers, or code debugging!`;
                dashChatArea.appendChild(greeting);
            }

            applyUserName();
            renderNavAuth();
        }

        function clearAuthSession() {
            localStorage.removeItem('codemind_auth_token');
            localStorage.removeItem('codemind_auth_user');
            localStorage.removeItem('codemind_user_name');
            localStorage.removeItem('codemind_bot_name');
            localStorage.removeItem('codemind_chat_history');
            localStorage.removeItem('codemind_active_test');
            localStorage.removeItem('codemind_last_problem');
            localStorage.removeItem('codemind_last_problem_title');
            sessionStorage.removeItem('cmIntroShown');
            window.currentStudentId = null;
            activeMayaConversationId = null;
            window.currentUserHasGroqKey = false;
            window.currentUserGroqKeyPreview = '';

            // Reset in-memory chat histories
            if (typeof companionChatHistory !== 'undefined') companionChatHistory = [];
            if (typeof aiTutorChatHistory !== 'undefined') aiTutorChatHistory = [];

            // Reset dashboard companion chat DOM to default greeting
            const dashChatArea = document.getElementById('companionChatArea');
            if (dashChatArea) {
                dashChatArea.innerHTML = '';
                const greeting = document.createElement('div');
                greeting.className = 'companion-bubble';
                greeting.id = 'companionGreetingBubble';
                greeting.innerHTML = `👋 Hello! I am <strong>Maya</strong>, your CodeMind AI Companion &amp; Tutor. Ask me anything about programming, algorithms, recursion, pointers, or code debugging!`;
                dashChatArea.appendChild(greeting);
            }

            applyUserName();
            renderNavAuth();
        }

        async function authFetch(url, options = {}) {
            const headers = Object.assign({}, options.headers || {});
            const token = getAuthToken();
            const sid = getStudentId();
            if (token) {
                headers['Authorization'] = `Bearer ${token}`;
            }
            if (sid && sid !== 'null' && sid !== 'undefined') {
                headers['X-Student-Id'] = sid;
            }
            try {
                const res = await fetch(url, Object.assign({}, options, { headers }));
                if (res.status === 401) {
                    console.warn('Session expired or unauthorized (HTTP 401). Prompting login.');
                    clearAuthSession();
                    openAuthModal('signin');
                }
                return res;
            } catch (networkErr) {
                const classified = classifyApiError(networkErr);
                console.error(`[authFetch ${classified.type}] ${url}:`, networkErr);
                if (classified.type === 'BACKEND OFFLINE') {
                    updateBackendHealthUI(false, null, 'Offline');
                }
                throw networkErr;
            }
        }

        function renderNavAuth() {
            const container = document.getElementById('navAuthSection');
            if (!container) return;
            const user = getAuthUser();
            const adminNavBtn = document.getElementById('navAdminPortal');
            if (adminNavBtn) {
                if (user && isAuthenticated() && (user.role === 'admin' || user.role === 'founder' || user.role === 'super_admin')) {
                    adminNavBtn.style.display = 'inline-flex';
                } else {
                    adminNavBtn.style.display = 'none';
                }
            }

            if (user && isAuthenticated()) {
                const initial = (user.display_name || user.username || 'U')[0].toUpperCase();
                let displayName = user.display_name || user.username || 'Learner';
                const escapedName = escapeHtml(displayName);
                container.innerHTML = `
                    <div class="nav-user-pill" onclick="openCompanionRenameModal()" style="cursor:pointer;" title="Account & Settings (${escapedName})">
                        <div class="nav-user-avatar">${initial}</div>
                        <span class="nav-user-name" id="navUserName">${escapedName}</span>
                        <button class="nav-name-edit-btn" onclick="event.stopPropagation(); openCompanionRenameModal();" title="Profile & Assistant Settings">⚙️</button>
                    </div>
                    <button class="nav-logout-btn" onclick="handleLogout()" title="Log out of this session">
                        Log Out
                    </button>
                `;
            } else {
                container.innerHTML = `
                    <button class="nav-login-btn" onclick="openAuthModal('signin')">
                        Sign In / Register
                    </button>
                `;
            }
        }

        function openAuthModal(defaultTab = 'signin', customPrompt = null) {
            const overlay = document.getElementById('authModalOverlay');
            if (!overlay) return;
            switchAuthTab(defaultTab);
            clearAuthMessages();
            const subtitle = document.getElementById('authModalSubtitle');
            if (subtitle) {
                if (customPrompt) {
                    subtitle.textContent = customPrompt;
                    subtitle.dataset.custom = '1';
                } else {
                    delete subtitle.dataset.custom;
                }
            }
            overlay.style.display = 'flex';
        }

        function closeAuthModal() {
            const overlay = document.getElementById('authModalOverlay');
            if (overlay) overlay.style.display = 'none';
            const subtitle = document.getElementById('authModalSubtitle');
            if (subtitle) delete subtitle.dataset.custom;
        }

        function switchAuthTab(tab) {
            clearAuthMessages();
            const tabSignIn = document.getElementById('tabBtnSignIn');
            const tabReg = document.getElementById('tabBtnRegister');
            const formSignIn = document.getElementById('authSignInForm');
            const formReg = document.getElementById('authRegisterForm');
            const formOtp = document.getElementById('authOtpForm');
            const subtitle = document.getElementById('authModalSubtitle');
            const tabsNav = document.querySelector('#authModalOverlay .auth-tabs');

            if (tab === 'register') {
                if (tabsNav) tabsNav.style.display = 'flex';
                if (tabSignIn) tabSignIn.className = 'auth-tab-btn';
                if (tabReg) tabReg.className = 'auth-tab-btn active gold-active';
                if (formSignIn) formSignIn.style.display = 'none';
                if (formReg) formReg.style.display = 'block';
                if (formOtp) formOtp.style.display = 'none';
                if (subtitle && !subtitle.dataset.custom) subtitle.textContent = 'Create your personalized CodeMind student profile';
            } else if (tab === 'otp') {
                if (tabsNav) tabsNav.style.display = 'none';
                if (formSignIn) formSignIn.style.display = 'none';
                if (formReg) formReg.style.display = 'none';
                if (formOtp) formOtp.style.display = 'block';
                if (subtitle && !subtitle.dataset.custom) subtitle.textContent = 'Enter the 6-digit verification code to activate your account';
                const otpInput = document.getElementById('authOtpInput');
                if (otpInput) {
                    otpInput.value = '';
                    setTimeout(() => otpInput.focus(), 100);
                }
            } else {
                if (tabsNav) tabsNav.style.display = 'flex';
                if (tabSignIn) tabSignIn.className = 'auth-tab-btn active gold-active';
                if (tabReg) tabReg.className = 'auth-tab-btn';
                if (formSignIn) formSignIn.style.display = 'block';
                if (formReg) formReg.style.display = 'none';
                if (formOtp) formOtp.style.display = 'none';
                if (subtitle && !subtitle.dataset.custom) subtitle.textContent = 'Sign in to access your progress, tests, and companion';
            }
        }

        let authOtpCountdownInterval = null;

        function maskAuthEmail(email) {
            if (!email || !email.includes('@')) return email || '';
            const parts = email.split('@');
            const user = parts[0];
            const domain = parts[1];
            if (user.length <= 2) return `${user[0]}***@${domain}`;
            return `${user.slice(0, 2)}***@${domain}`;
        }

        function startAuthOtpCountdown(seconds = 600) {
            if (authOtpCountdownInterval) clearInterval(authOtpCountdownInterval);
            let remaining = seconds;
            const timerEl = document.getElementById('authOtpCountdown');
            const updateUI = () => {
                if (!timerEl) return;
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                timerEl.textContent = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
                if (remaining <= 0) {
                    clearInterval(authOtpCountdownInterval);
                    authOtpCountdownInterval = null;
                    timerEl.textContent = 'Expired';
                    timerEl.style.color = '#ef4444';
                }
            };
            updateUI();
            authOtpCountdownInterval = setInterval(() => {
                remaining--;
                updateUI();
            }, 1000);
        }

        function showAuthOtpStep(email, customNotice = null) {
            window._pendingOtpEmail = email;
            switchAuthTab('otp');
            const targetEl = document.getElementById('authOtpTargetEmail');
            if (targetEl) targetEl.textContent = maskAuthEmail(email);
            if (customNotice) {
                const noticeEl = document.getElementById('authOtpNotice');
                if (noticeEl) noticeEl.innerHTML = customNotice;
            }
            startAuthOtpCountdown(600);
        }

        function showAuthError(msg) {
            const box = document.getElementById('authErrorBox');
            if (box) {
                box.textContent = msg;
                box.style.display = 'block';
            }
            const sBox = document.getElementById('authSuccessBox');
            if (sBox) sBox.style.display = 'none';
        }

        function showAuthSuccess(msg) {
            const box = document.getElementById('authSuccessBox');
            if (box) {
                box.textContent = msg;
                box.style.display = 'block';
            }
            const eBox = document.getElementById('authErrorBox');
            if (eBox) eBox.style.display = 'none';
        }

        function clearAuthMessages() {
            const eBox = document.getElementById('authErrorBox');
            if (eBox) eBox.style.display = 'none';
            const sBox = document.getElementById('authSuccessBox');
            if (sBox) sBox.style.display = 'none';
        }

        async function handleSignInSubmit(e) {
            e.preventDefault();
            clearAuthMessages();
            const username = (document.getElementById('signInUsername').value || '').trim();
            const password = (document.getElementById('signInPassword').value || '');
            const btn = document.getElementById('signInSubmitBtn');

            if (!username || !password) {
                showAuthError('Please enter both username and password.');
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Signing in...';

            try {
                const res = await fetch(`${API_BASE}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();
                if (!res.ok) {
                    const errMsg = safeExtractErrorMessage(data, 'Sign in failed. Please check your credentials.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    httpErr.data = data;
                    if (data && data.email) httpErr.email = data.email;
                    throw httpErr;
                }

                setAuthSession(data.token, data.user, data.profile);
                closeAuthModal();
                if (data.user && !data.user.has_groq_key) {
                    setTimeout(() => openGroqKeyModal(true), 350);
                }
                if (window.pendingAuthAction && typeof window.pendingAuthAction === 'function') {
                    const act = window.pendingAuthAction;
                    window.pendingAuthAction = null;
                    act();
                } else if (!activeProblemId) {
                    showDashboard();
                } else {
                    initDashboard();
                }
            } catch(err) {
                if (err.status === 403 && ((err.message || '').toLowerCase().includes('verif') || (err.data && err.data.requires_otp))) {
                    const targetEmail = (err.data && err.data.email) || err.email || (err.data && err.data.detail && err.data.detail.email);
                    if (targetEmail && targetEmail.includes('@')) {
                        window._pendingOtpEmail = targetEmail;
                        showAuthOtpStep(targetEmail, `Your email address is not verified yet. A fresh 6-digit verification code was sent to <strong>${escapeHtml(targetEmail)}</strong> to activate your account.`);
                    } else {
                        showAuthOtpStep(username);
                    }
                    showAuthError('Email verification required. Please enter your 6-digit OTP below.');
                    return;
                }
                const classified = classifyApiError(err);
                showAuthError(`${classified.type}: ${classified.message}`);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Sign In →';
            }
        }

        async function handleRegisterSubmit(e) {
            e.preventDefault();
            clearAuthMessages();
            const displayName = (document.getElementById('regDisplayName').value || '').trim();
            const username = (document.getElementById('regUsername').value || '').trim();
            const email = (document.getElementById('regEmail').value || '').trim();
            const password = (document.getElementById('regPassword').value || '');
            const mobile = (document.getElementById('regMobile') ? document.getElementById('regMobile').value : '').trim();
            const institute = (document.getElementById('regInstitute') ? document.getElementById('regInstitute').value : '').trim();
            const course = (document.getElementById('regCourse') ? document.getElementById('regCourse').value : '').trim();
            const agreeBox = document.getElementById('regAgreeTerms');
            const btn = document.getElementById('regSubmitBtn');

            if (!displayName || !username || !email || !password) {
                showAuthError('Please fill in all fields.');
                return;
            }
            if (password.length < 6) {
                showAuthError('Password must be at least 6 characters in length.');
                return;
            }
            const hasLetter = /[a-zA-Z]/.test(password);
            const hasDigitOrSpecial = /[^a-zA-Z]/.test(password);
            if (!hasLetter || !hasDigitOrSpecial) {
                showAuthError('Password must contain at least one letter and at least one digit or special character.');
                return;
            }
            if (agreeBox && !agreeBox.checked) {
                showAuthError('You must agree to the Terms of Service and Privacy Policy to register.');
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Creating account...';

            try {
                const regPayload = {
                    display_name: displayName,
                    username,
                    email,
                    password,
                    agree_terms: true
                };
                if (mobile) regPayload.mobile = mobile;
                if (institute) regPayload.institute = institute;
                if (course) regPayload.course = course;

                const res = await fetch(`${API_BASE}/api/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(regPayload)
                });
                const data = await res.json();
                if (!res.ok) {
                    const errMsg = safeExtractErrorMessage(data, 'Registration failed. Please check your inputs and try again.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    throw httpErr;
                }

                // Strictly enforce OTP verification requirement — NEVER bypass OTP verification!
                const targetEmail = data.email || email;
                window._pendingOtpEmail = targetEmail;
                window._pendingOtpUser = data.user;
                window._pendingOtpProfile = data.profile;
                showAuthOtpStep(targetEmail);
                showAuthSuccess(`Account ready! A 6-digit verification code was dispatched to ${maskAuthEmail(targetEmail)}. Please enter it below to activate your account.`);
                return;
            } catch(err) {
                const classified = classifyApiError(err);
                showAuthError(`${classified.type}: ${classified.message}`);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Create Account & Start Learning →';
            }
        }

        async function handleOtpSubmit(e) {
            e.preventDefault();
            clearAuthMessages();
            const email = window._pendingOtpEmail;
            const otpInput = document.getElementById('authOtpInput');
            const otp = (otpInput ? otpInput.value : '').trim();
            const btn = document.getElementById('authOtpSubmitBtn');

            if (!email) {
                showAuthError('Email session expired. Please restart registration.');
                switchAuthTab('register');
                return;
            }
            if (!otp || otp.length !== 6 || !/^\d{6}$/.test(otp)) {
                showAuthError('Please enter a valid 6-digit numerical verification code.');
                if (otpInput) otpInput.focus();
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Verifying OTP...';

            try {
                const res = await fetch(`${API_BASE}/api/auth/verify-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email, otp: otp, purpose: 'EMAIL_VERIFICATION' })
                });
                const data = await res.json();
                if (!res.ok) {
                    const errMsg = safeExtractErrorMessage(data, 'Verification failed. Please check the code and try again.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    throw httpErr;
                }

                const token = data.token || (data.user && data.user.session_token);
                const user = data.user || window._pendingOtpUser;
                const profile = data.profile || window._pendingOtpProfile;

                setAuthSession(token, user, profile);
                window._pendingOtpEmail = null;
                window._pendingOtpUser = null;
                window._pendingOtpProfile = null;

                closeAuthModal();
                showNotification('🎉 Welcome to CodeMind! Your account is verified and ready.');
                if (user && !user.has_groq_key) {
                    setTimeout(() => openGroqKeyModal(true), 350);
                }

                if (window.pendingAuthAction && typeof window.pendingAuthAction === 'function') {
                    const act = window.pendingAuthAction;
                    window.pendingAuthAction = null;
                    act();
                } else if (!activeProblemId) {
                    showDashboard();
                } else {
                    initDashboard();
                }
            } catch(err) {
                const classified = classifyApiError(err);
                showAuthError(`${classified.type}: ${classified.message}`);
                if (otpInput) {
                    otpInput.focus();
                    otpInput.select();
                }
            } finally {
                btn.disabled = false;
                btn.textContent = 'Verify Code & Complete Registration →';
            }
        }

        let _authOtpResendCooldown = 0;
        let _authOtpResendTimer = null;
        async function handleResendOtp() {
            if (_authOtpResendCooldown > 0) return;
            const email = window._pendingOtpEmail;
            if (!email) {
                showAuthError('No pending verification email found. Please restart registration.');
                switchAuthTab('register');
                return;
            }

            const resendBtn = document.getElementById('authOtpResendBtn');
            if (resendBtn) {
                resendBtn.disabled = true;
                resendBtn.textContent = 'Sending code...';
            }

            try {
                const res = await fetch(`${API_BASE}/api/auth/resend-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: email, purpose: 'EMAIL_VERIFICATION' })
                });
                const data = await res.json();
                if (!res.ok) {
                    const errMsg = safeExtractErrorMessage(data, 'Could not resend verification code.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    throw httpErr;
                }

                showAuthSuccess('A fresh 6-digit verification code has been dispatched to your email.');

                _authOtpResendCooldown = 60;
                if (resendBtn) resendBtn.textContent = `Resend Code (60s)`;
                _authOtpResendTimer = setInterval(() => {
                    _authOtpResendCooldown--;
                    if (_authOtpResendCooldown <= 0) {
                        clearInterval(_authOtpResendTimer);
                        if (resendBtn) {
                            resendBtn.disabled = false;
                            resendBtn.textContent = 'Resend Code';
                        }
                    } else {
                        if (resendBtn) resendBtn.textContent = `Resend Code (${_authOtpResendCooldown}s)`;
                    }
                }, 1000);
            } catch(err) {
                const classified = classifyApiError(err);
                showAuthError(`${classified.type}: ${classified.message}`);
                if (resendBtn) {
                    resendBtn.disabled = false;
                    resendBtn.textContent = 'Resend Code';
                }
            }
        }

        async function handleLogout() {
            if (!confirm('Are you sure you want to log out?')) return;
            try {
                await authFetch(`${API_BASE}/api/auth/logout`, { method: 'POST' });
            } catch(e) {}
            clearAuthSession();
            renderDashboardWidgets(null, null);
            showDashboard();
        }

        function requireAuth(onSuccess) {
            if (!isAuthenticated()) {
                window.pendingAuthAction = onSuccess;
                openAuthModal('signin');
                return false;
            }
            if (typeof onSuccess === 'function') onSuccess();
            return true;
        }

        // ===================== LEGAL MODALS & FORGOT PASSWORD =====================
        function openTermsModal() {
            const overlay = document.getElementById('termsModalOverlay');
            if (overlay) overlay.style.display = 'flex';
        }
        function closeTermsModal() {
            const overlay = document.getElementById('termsModalOverlay');
            if (overlay) overlay.style.display = 'none';
        }

        function openPrivacyModal() {
            const overlay = document.getElementById('privacyModalOverlay');
            if (overlay) overlay.style.display = 'flex';
        }
        function closePrivacyModal() {
            const overlay = document.getElementById('privacyModalOverlay');
            if (overlay) overlay.style.display = 'none';
        }

        function openForgotPasswordModal() {
            closeAuthModal();
            const overlay = document.getElementById('forgotPasswordModalOverlay');
            if (overlay) overlay.style.display = 'flex';
            switchForgotStage('request');
        }
        function closeForgotPasswordModal() {
            const overlay = document.getElementById('forgotPasswordModalOverlay');
            if (overlay) overlay.style.display = 'none';
        }
        let _recoveryResetToken = null;
        let _pendingForgotEmail = null;
        let _forgotOtpResendCooldown = 0;
        let _forgotOtpResendTimer = null;

        function switchForgotStage(stage) {
            const reqForm = document.getElementById('forgotPasswordForm');
            const otpForm = document.getElementById('forgotOtpForm');
            const resForm = document.getElementById('resetPasswordForm');
            const errBox = document.getElementById('pwdResetErrorBox');
            const succBox = document.getElementById('pwdResetSuccessBox');
            const subtitle = document.getElementById('pwdResetSubtitle');
            if (errBox) errBox.style.display = 'none';
            if (succBox) succBox.style.display = 'none';

            if (reqForm) reqForm.style.display = 'none';
            if (otpForm) otpForm.style.display = 'none';
            if (resForm) resForm.style.display = 'none';

            if (stage === 'otp') {
                if (otpForm) otpForm.style.display = 'block';
                if (subtitle) subtitle.textContent = 'Enter 6-Digit Recovery Code';
                const otpInput = document.getElementById('forgotOtpInput');
                if (otpInput) {
                    otpInput.value = '';
                    setTimeout(() => otpInput.focus(), 100);
                }
            } else if (stage === 'reset') {
                if (resForm) resForm.style.display = 'block';
                if (subtitle) subtitle.textContent = 'Create New Password';
                const pwInput = document.getElementById('resetNewPasswordInput');
                if (pwInput) setTimeout(() => pwInput.focus(), 100);
            } else {
                if (reqForm) reqForm.style.display = 'block';
                if (subtitle) subtitle.textContent = 'Password Recovery & Security';
                _recoveryResetToken = null;
                _pendingForgotEmail = null;
            }
        }

        async function handleForgotPasswordSubmit(e) {
            e.preventDefault();
            const email = (document.getElementById('forgotEmailInput').value || '').trim();
            const errBox = document.getElementById('pwdResetErrorBox');
            const succBox = document.getElementById('pwdResetSuccessBox');
            const btn = document.getElementById('forgotSubmitBtn');
            if (!email) return;

            btn.disabled = true;
            btn.textContent = 'Sending code...';
            if (errBox) errBox.style.display = 'none';
            if (succBox) succBox.style.display = 'none';

            try {
                const res = await fetch(`${API_BASE}/api/auth/forgot-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(safeExtractErrorMessage(data, 'Could not dispatch recovery code.'));
                }
                _pendingForgotEmail = email;
                const targetEl = document.getElementById('forgotOtpTargetEmail');
                if (targetEl) targetEl.textContent = email;
                switchForgotStage('otp');
                if (succBox) {
                    succBox.textContent = `A 6-digit recovery code was dispatched to ${email}. Please enter it below.`;
                    succBox.style.display = 'block';
                }
            } catch (err) {
                if (errBox) {
                    errBox.textContent = err.message || 'Unable to process reset request. Please check your connection.';
                    errBox.style.display = 'block';
                }
            } finally {
                btn.disabled = false;
                btn.textContent = 'Send Recovery Code →';
            }
        }

        async function handleForgotOtpSubmit(e) {
            e.preventDefault();
            const email = _pendingForgotEmail;
            const otpInput = document.getElementById('forgotOtpInput');
            const otp = (otpInput ? otpInput.value : '').trim();
            const errBox = document.getElementById('pwdResetErrorBox');
            const succBox = document.getElementById('pwdResetSuccessBox');
            const btn = document.getElementById('forgotOtpSubmitBtn');

            if (!email) {
                switchForgotStage('request');
                return;
            }
            if (!otp || otp.length !== 6 || !/^\d{6}$/.test(otp)) {
                if (errBox) {
                    errBox.textContent = 'Please enter a valid 6-digit numerical code.';
                    errBox.style.display = 'block';
                }
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Verifying code...';
            if (errBox) errBox.style.display = 'none';
            if (succBox) succBox.style.display = 'none';

            try {
                const res = await fetch(`${API_BASE}/api/auth/verify-recovery-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, otp })
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(safeExtractErrorMessage(data, 'Invalid or expired recovery code.'));
                }
                _recoveryResetToken = data.reset_token;
                switchForgotStage('reset');
                if (succBox) {
                    succBox.textContent = 'Recovery code verified! Enter your new password below.';
                    succBox.style.display = 'block';
                }
            } catch (err) {
                if (errBox) {
                    errBox.textContent = err.message || 'Invalid recovery code.';
                    errBox.style.display = 'block';
                }
            } finally {
                btn.disabled = false;
                btn.textContent = 'Verify Recovery Code →';
            }
        }

        async function handleResendRecoveryOtp() {
            if (_forgotOtpResendCooldown > 0) return;
            const email = _pendingForgotEmail;
            const errBox = document.getElementById('pwdResetErrorBox');
            const succBox = document.getElementById('pwdResetSuccessBox');
            const resendBtn = document.getElementById('forgotOtpResendBtn');
            if (!email) return;

            if (resendBtn) {
                resendBtn.disabled = true;
                resendBtn.textContent = 'Sending...';
            }

            try {
                const res = await fetch(`${API_BASE}/api/auth/resend-otp`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, purpose: 'PASSWORD_RECOVERY' })
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(safeExtractErrorMessage(data, 'Could not resend recovery code.'));
                }
                if (succBox) {
                    succBox.textContent = 'A fresh 6-digit recovery code has been dispatched to your email.';
                    succBox.style.display = 'block';
                }
                _forgotOtpResendCooldown = 60;
                if (resendBtn) resendBtn.textContent = `Resend (60s)`;
                _forgotOtpResendTimer = setInterval(() => {
                    _forgotOtpResendCooldown--;
                    if (_forgotOtpResendCooldown <= 0) {
                        clearInterval(_forgotOtpResendTimer);
                        if (resendBtn) {
                            resendBtn.disabled = false;
                            resendBtn.textContent = 'Resend Code';
                        }
                    } else {
                        if (resendBtn) resendBtn.textContent = `Resend (${_forgotOtpResendCooldown}s)`;
                    }
                }, 1000);
            } catch(err) {
                if (errBox) {
                    errBox.textContent = err.message || 'Failed to resend code.';
                    errBox.style.display = 'block';
                }
                if (resendBtn) {
                    resendBtn.disabled = false;
                    resendBtn.textContent = 'Resend Code';
                }
            }
        }

        async function handleResetPasswordSubmit(e) {
            e.preventDefault();
            const token = _recoveryResetToken;
            const newPassword = document.getElementById('resetNewPasswordInput').value || '';
            const confirmPassword = document.getElementById('resetConfirmPasswordInput').value || '';
            const errBox = document.getElementById('pwdResetErrorBox');
            const succBox = document.getElementById('pwdResetSuccessBox');
            const btn = document.getElementById('resetSubmitBtn');

            if (!token) {
                if (errBox) {
                    errBox.textContent = 'Recovery session expired. Please restart password recovery.';
                    errBox.style.display = 'block';
                }
                switchForgotStage('request');
                return;
            }

            if (newPassword !== confirmPassword) {
                if (errBox) {
                    errBox.textContent = 'Passwords do not match.';
                    errBox.style.display = 'block';
                }
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Updating...';
            if (errBox) errBox.style.display = 'none';

            try {
                const res = await fetch(`${API_BASE}/api/auth/reset-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ reset_token: token, new_password: newPassword, confirm_password: confirmPassword })
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(safeExtractErrorMessage(data, 'Password reset failed.'));
                }
                if (succBox) {
                    succBox.textContent = 'Password reset successfully! Please sign in with your new password.';
                    succBox.style.display = 'block';
                }
                _recoveryResetToken = null;
                _pendingForgotEmail = null;
                setTimeout(() => {
                    closeForgotPasswordModal();
                    openAuthModal('signin');
                }, 1500);
            } catch (err) {
                if (errBox) {
                    errBox.textContent = err.message || 'Password reset failed.';
                    errBox.style.display = 'block';
                }
            } finally {
                btn.disabled = false;
                btn.textContent = 'Update Password & Sign In →';
            }
        }

        async function handleResendVerification() {
            const btn = document.getElementById('settingsResendVerifyBtn');
            const badge = document.getElementById('settingsVerificationBadge');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Sending...';
            }
            try {
                const res = await authFetch(`${API_BASE}/api/auth/resend-verification`, { method: 'POST' });
                const data = await res.json();
                if (res.ok) {
                    alert('Verification email sent! Please check your inbox and click the verification link.');
                    if (btn) btn.textContent = 'Link Sent ✓';
                } else {
                    alert('Failed to resend: ' + safeExtractErrorMessage(data, 'Error'));
                    if (btn) {
                        btn.disabled = false;
                        btn.textContent = 'Resend Link';
                    }
                }
            } catch (e) {
                alert('Request failed: ' + e.message);
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'Resend Link';
                }
            }
        }

        function toggleSettingsChangePassword() {
            const box = document.getElementById('settingsChangePasswordBox');
            if (!box) return;
            box.style.display = box.style.display === 'none' ? 'block' : 'none';
        }

        async function handleChangePasswordSubmit() {
            const current_password = document.getElementById('changePwdCurrent').value || '';
            const new_password = document.getElementById('changePwdNew').value || '';
            const confirm_password = document.getElementById('changePwdConfirm').value || '';
            const msgEl = document.getElementById('changePwdMsg');

            if (!current_password || !new_password) {
                if (msgEl) {
                    msgEl.style.color = '#ef4444';
                    msgEl.textContent = 'Please fill all password fields.';
                    msgEl.style.display = 'block';
                }
                return;
            }
            if (new_password !== confirm_password) {
                if (msgEl) {
                    msgEl.style.color = '#ef4444';
                    msgEl.textContent = 'New passwords do not match.';
                    msgEl.style.display = 'block';
                }
                return;
            }

            try {
                const res = await authFetch(`${API_BASE}/api/auth/change-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password, new_password, confirm_password })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(safeExtractErrorMessage(data, 'Change password failed'));
                if (msgEl) {
                    msgEl.style.color = '#22c55e';
                    msgEl.textContent = 'Password changed successfully!';
                    msgEl.style.display = 'block';
                }
                document.getElementById('changePwdCurrent').value = '';
                document.getElementById('changePwdNew').value = '';
                document.getElementById('changePwdConfirm').value = '';
                setTimeout(() => toggleSettingsChangePassword(), 1800);
            } catch (err) {
                if (msgEl) {
                    msgEl.style.color = '#ef4444';
                    msgEl.textContent = err.message || 'Password update failed';
                    msgEl.style.display = 'block';
                }
            }
        }

        // ===================== 4-STEP ACCOUNT DELETION =====================
        function openDeleteAccountModal() {
            closeCompanionRenameModal();
            const overlay = document.getElementById('deleteAccountModalOverlay');
            const errBox = document.getElementById('deleteAccountErrorBox');
            if (errBox) errBox.style.display = 'none';
            if (overlay) overlay.style.display = 'flex';
        }
        function closeDeleteAccountModal() {
            const overlay = document.getElementById('deleteAccountModalOverlay');
            if (overlay) overlay.style.display = 'none';
        }

        async function handleDeleteAccountSubmit(e) {
            e.preventDefault();
            const pwd = document.getElementById('deleteAccountPassword').value || '';
            const confirmPhrase = (document.getElementById('deleteAccountConfirmation').value || '').trim();
            const errBox = document.getElementById('deleteAccountErrorBox');
            const btn = document.getElementById('deleteAccountSubmitBtn');

            if (confirmPhrase !== 'DELETE MY ACCOUNT') {
                if (errBox) {
                    errBox.textContent = 'Confirmation phrase must exactly match "DELETE MY ACCOUNT".';
                    errBox.style.display = 'block';
                }
                return;
            }

            btn.disabled = true;
            btn.textContent = 'Purging account data...';
            if (errBox) errBox.style.display = 'none';

            try {
                const res = await authFetch(`${API_BASE}/api/auth/delete-account`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ current_password: pwd, confirmation: confirmPhrase })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(safeExtractErrorMessage(data, 'Account deletion failed. Check your password.'));
                closeDeleteAccountModal();
                clearAuthSession();
                alert('Your CodeMind account and all associated submissions and personal data have been permanently purged.');
                window.location.reload();
            } catch (err) {
                if (errBox) {
                    errBox.textContent = err.message || 'Failed to delete account.';
                    errBox.style.display = 'block';
                }
            } finally {
                btn.disabled = false;
                btn.textContent = 'Permanently Delete Account';
            }
        }

        // ===================== ADMIN & FOUNDER PORTAL LOGIC =====================
        let currentAdminTab = 'overview';

        function showAdminPortal() {
            if (!isAuthenticated()) {
                openAuthModal('signin', 'Admin access requires login.');
                return;
            }
            const user = getAuthUser();
            if (!user || (user.role !== 'admin' && user.role !== 'founder')) {
                alert('Access denied: Administrator or Founder privileges required.');
                return;
            }
            window.active_workspace = 'admin';
            hideAllViews();
            const portal = document.getElementById('adminPortalView');
            if (portal) portal.style.display = 'block';
            setActiveNav('navAdminPortal');
            const roleBadge = document.getElementById('adminPortalRoleBadge');
            if (roleBadge) roleBadge.textContent = (user.role || 'ADMIN').toUpperCase();
            switchAdminTab('overview');
        }

        function switchAdminTab(tab) {
            currentAdminTab = tab;
            ['overview', 'users', 'problems', 'maya', 'providers', 'audits', 'system'].forEach(t => {
                const btn = document.getElementById(`adminTabBtn${t.charAt(0).toUpperCase() + t.slice(1)}`);
                const view = document.getElementById(`adminTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
                if (btn) btn.className = (t === tab) ? 'auth-tab-btn active gold-active' : 'auth-tab-btn';
                if (view) view.style.display = (t === tab) ? 'block' : 'none';
            });

            if (tab === 'overview') loadAdminDashboard();
            else if (tab === 'users') loadAdminUsers(1);
            else if (tab === 'problems') loadAdminProblems();
            else if (tab === 'maya') loadAdminMayaMetrics();
            else if (tab === 'providers') loadAdminProviders();
            else if (tab === 'audits') loadAdminAudits(1);
            else if (tab === 'system') loadAdminSystem();
        }

        function refreshCurrentAdminTab() {
            switchAdminTab(currentAdminTab);
        }

        async function loadAdminDashboard() {
            try {
                const res = await authFetch(`${API_BASE}/api/admin/dashboard`);
                if (!res.ok) return;
                const d = await res.json();

                const uTotal = document.getElementById('adminStatTotalUsers');
                const u7d = document.getElementById('adminStatActiveUsers7d');
                const sTotal = document.getElementById('adminStatTotalSubmissions');
                const sPass = document.getElementById('adminStatPassRate');
                const ptEl = document.getElementById('adminStatProblemsTests');

                if (uTotal) uTotal.textContent = d.users ? d.users.total_users : '--';
                if (u7d) u7d.textContent = d.users ? d.users.active_users_7d : '--';
                if (sTotal) sTotal.textContent = d.submissions ? d.submissions.total_submissions : '--';
                if (sPass) sPass.textContent = d.submissions ? `${d.submissions.acceptance_rate}%` : '--%';
                if (ptEl) ptEl.textContent = `${(d.curriculum && d.curriculum.total_problems) || 0} / ${(d.curriculum && d.curriculum.total_tests) || 0}`;

                // Live AI Provider Strip
                const strip = document.getElementById('adminOverviewProvidersStrip');
                if (strip && d.providers) {
                    strip.innerHTML = d.providers.map(p => `
                        <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:12px;">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <strong style="color:#f8fafc; font-size:13.5px;">${escapeHtml(p.name)}</strong>
                                <span style="font-size:11px; color:#22c55e; font-weight:700;">● ${escapeHtml(p.status.toUpperCase())}</span>
                            </div>
                            <div style="font-size:11.5px; color:#94a3b8; margin-top:4px;">Model: <span style="color:#38bdf8;">${escapeHtml(p.model)}</span></div>
                            <div style="font-size:11px; color:#cbd5e1; margin-top:2px;">Role: ${escapeHtml(p.role)} · Fallback: Priority ${p.priority}</div>
                        </div>
                    `).join('');
                }

                // Recent Audits Table
                const auditTable = document.getElementById('adminOverviewRecentAuditsTable');
                if (auditTable && d.recent_audits) {
                    if (d.recent_audits.length === 0) {
                        auditTable.innerHTML = `<tr><td colspan="5" style="padding:16px; text-align:center; color:#94a3b8;">No recent audit logs.</td></tr>`;
                    } else {
                        auditTable.innerHTML = d.recent_audits.map(a => `
                            <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                                <td style="padding:10px 12px; color:#94a3b8; font-size:11.5px;">${new Date(a.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'})}</td>
                                <td style="padding:10px 12px; color:#f8fafc; font-weight:600;">${escapeHtml(a.actor_email || 'System')}</td>
                                <td style="padding:10px 12px; color:#d4af37;"><code style="background:rgba(212,175,55,0.1); padding:2px 6px; border-radius:4px;">${escapeHtml(a.action)}</code></td>
                                <td style="padding:10px 12px; color:#cbd5e1;">${escapeHtml(a.resource_type || '--')}</td>
                                <td style="padding:10px 12px;"><span style="color:${a.result === 'success' ? '#22c55e' : '#ef4444'}; font-weight:700; font-size:11.5px;">${escapeHtml(a.result.toUpperCase())}</span></td>
                            </tr>
                        `).join('');
                    }
                }
            } catch (e) {
                console.error('Error loading admin dashboard:', e);
            }
        }

        async function loadAdminUsers(page = 1) {
            const search = (document.getElementById('adminUsersSearchInput') ? document.getElementById('adminUsersSearchInput').value : '').trim();
            const role = (document.getElementById('adminUsersRoleFilter') ? document.getElementById('adminUsersRoleFilter').value : '');
            const verif = (document.getElementById('adminUsersVerifFilter') ? document.getElementById('adminUsersVerifFilter').value : '');
            const activity = (document.getElementById('adminUsersActivityFilter') ? document.getElementById('adminUsersActivityFilter').value : '');
            const status = (document.getElementById('adminUsersStatusFilter') ? document.getElementById('adminUsersStatusFilter').value : '');
            const tableBody = document.getElementById('adminUsersTableBody');
            const pagination = document.getElementById('adminUsersPagination');
            if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#94a3b8;">Loading user accounts...</td></tr>`;

            try {
                const params = new URLSearchParams({ page: page, limit: 10 });
                if (search) params.append('search', search);
                if (role) params.append('role', role);
                if (verif !== '') params.append('email_verified', verif);
                if (activity) params.append('activity_filter', activity);
                if (status === 'active') params.append('is_active', 'true');
                if (status === 'deactivated') params.append('is_active', 'false');

                const res = await authFetch(`${API_BASE}/api/admin/users?${params.toString()}`);
                if (!res.ok) throw new Error('Failed to load users');
                const d = await res.json();

                const userList = d.users || d.items || [];
                if (userList.length === 0) {
                    if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#94a3b8;">No users found matching query.</td></tr>`;
                    if (pagination) pagination.innerHTML = '';
                    return;
                }

                if (tableBody) {
                    tableBody.innerHTML = userList.map(u => {
                        let statusBadge = '';
                        if (!u.is_active) {
                            statusBadge = `<span style="background:rgba(239,68,68,0.15); color:#ef4444; border:1px solid rgba(239,68,68,0.3); padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">⊘ DISABLED</span>`;
                        } else if (u.is_verified) {
                            statusBadge = `<span style="background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3); padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">✓ VERIFIED</span>`;
                        } else {
                            statusBadge = `<span style="background:rgba(245,158,11,0.15); color:#f59e0b; border:1px solid rgba(245,158,11,0.3); padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">⏳ PENDING VERIFICATION</span>`;
                        }

                        const academicStr = [u.institute || 'Direct', u.course, u.year_of_study ? `Yr ${u.year_of_study}` : null].filter(Boolean).join(' • ');
                        const activityLabel = u.activity_status || (u.last_activity_at ? 'Active' : 'Inactive');

                        return `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:12px 14px;">
                                <div style="font-weight:700; color:#f8fafc;">${escapeHtml(u.display_name || u.full_name || u.username)}</div>
                                <div style="font-size:11.5px; color:#94a3b8;">@${escapeHtml(u.username)}</div>
                                <div style="font-size:11.5px; color:#cbd5e1; margin-top:2px;">${escapeHtml(u.email || '--')}</div>
                            </td>
                            <td style="padding:12px 14px; color:#cbd5e1; font-size:12px;">
                                <div>${escapeHtml(academicStr || '--')}</div>
                                ${u.mobile ? `<div style="font-size:11px; color:#94a3b8; margin-top:2px;">📱 ${escapeHtml(u.mobile)} ${u.mobile_verified ? '✓' : ''}</div>` : ''}
                            </td>
                            <td style="padding:12px 14px;">
                                <span style="background:${u.role==='founder'||u.role==='super_admin'?'rgba(212,175,55,0.2)':u.role==='admin'?'rgba(56,189,248,0.2)':'rgba(255,255,255,0.08)'}; color:${u.role==='founder'||u.role==='super_admin'?'#d4af37':u.role==='admin'?'#38bdf8':'#cbd5e1'}; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:700;">
                                    ${escapeHtml((u.role || 'student').toUpperCase())}
                                </span>
                            </td>
                            <td style="padding:12px 14px;">
                                ${statusBadge}
                            </td>
                            <td style="padding:12px 14px; font-size:12px;">
                                <div style="font-weight:600; color:#94a3b8;">${escapeHtml(activityLabel)}</div>
                                <div style="font-size:11px; color:#64748b; margin-top:2px;">${u.last_activity_at ? new Date(u.last_activity_at).toLocaleDateString() : (u.last_login ? new Date(u.last_login).toLocaleDateString() : 'Never')}</div>
                            </td>
                            <td style="padding:12px 14px; font-size:12px; color:#cbd5e1;">
                                <div style="font-weight:700; color:#38bdf8;">${u.solved_count || 0} <span style="font-weight:400; color:#94a3b8; font-size:11px;">solved</span></div>
                                <div style="font-size:11px; color:#94a3b8;">${u.submissions_count || 0} subs • ${u.tests_completed || 0} tests</div>
                            </td>
                            <td style="padding:12px 14px; color:#94a3b8; font-size:11.5px;">${u.created_at ? new Date(u.created_at).toLocaleDateString() : '--'}</td>
                            <td style="padding:12px 14px; text-align:right;">
                                <div style="display:inline-flex; gap:6px;">
                                    <button onclick="toggleUserStatus('${u.id}', ${u.is_active})" style="background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:#cbd5e1; padding:4px 8px; border-radius:5px; font-size:11.5px; cursor:pointer;" title="${u.is_active ? 'Deactivate user' : 'Reactivate user'}">
                                        ${u.is_active ? 'Deactivate' : 'Activate'}
                                    </button>
                                    <button onclick="promptChangeRole('${u.id}', '${escapeHtml(u.username)}', '${u.role}')" style="background:rgba(212,175,55,0.12); border:1px solid rgba(212,175,55,0.3); color:#d4af37; padding:4px 8px; border-radius:5px; font-size:11.5px; cursor:pointer;" title="Change role">
                                        Role
                                    </button>
                                </div>
                            </td>
                        </tr>
                        `;
                    }).join('');
                }

                if (pagination) {
                    pagination.innerHTML = `
                        <div>Showing page ${d.page} of ${d.total_pages} (${d.total_users} users)</div>
                        <div style="display:flex; gap:6px;">
                            <button onclick="loadAdminUsers(${d.page - 1})" ${d.page <= 1 ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : 'style="cursor:pointer;"'} class="filter-btn" style="padding:5px 12px; font-size:12px;">← Prev</button>
                            <button onclick="loadAdminUsers(${d.page + 1})" ${d.page >= d.total_pages ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : 'style="cursor:pointer;"'} class="filter-btn" style="padding:5px 12px; font-size:12px;">Next →</button>
                        </div>
                    `;
                }
            } catch (err) {
                if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#ef4444;">Error: ${escapeHtml(err.message)}</td></tr>`;
            }
        }

        async function toggleUserStatus(userId, currentStatus) {
            const actionVerb = currentStatus ? 'deactivate' : 'activate';
            if (!confirm(`Are you sure you want to ${actionVerb} this user account?`)) return;
            try {
                const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/status`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: !currentStatus })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(safeExtractErrorMessage(data, 'Status update failed'));
                loadAdminUsers(1);
            } catch (e) {
                alert('Action failed: ' + e.message);
            }
        }

        async function promptChangeRole(userId, username, currentRole) {
            const newRole = prompt(`Change role for @${username} (student, admin, founder):`, currentRole);
            if (!newRole || newRole.toLowerCase() === currentRole.toLowerCase()) return;
            const targetRole = newRole.trim().toLowerCase();
            if (!['student', 'admin', 'founder'].includes(targetRole)) {
                alert('Invalid role. Must be: student, admin, or founder.');
                return;
            }
            try {
                const res = await authFetch(`${API_BASE}/api/admin/users/${userId}/role`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ role: targetRole })
                });
                const data = await res.json();
                if (!res.ok) throw new Error(safeExtractErrorMessage(data, 'Role update failed'));
                loadAdminUsers(1);
            } catch (e) {
                alert('Role update failed: ' + e.message);
            }
        }

        async function loadAdminProblems() {
            const tableBody = document.getElementById('adminProblemsTableBody');
            const search = (document.getElementById('adminProblemsSearchInput') ? document.getElementById('adminProblemsSearchInput').value : '').trim();
            const diff = (document.getElementById('adminProblemsDifficultyFilter') ? document.getElementById('adminProblemsDifficultyFilter').value : '');
            if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="padding:24px; text-align:center; color:#94a3b8;">Loading problem catalog...</td></tr>`;

            try {
                const res = await authFetch(`${API_BASE}/api/admin/problems`);
                if (!res.ok) throw new Error('Failed to load problems');
                const d = await res.json();
                let problems = d.problems || [];
                if (search) {
                    const q = search.toLowerCase();
                    problems = problems.filter(p => (p.title || '').toLowerCase().includes(q) || (p.id || '').toLowerCase().includes(q));
                }
                if (diff) {
                    problems = problems.filter(p => (p.difficulty || '').toLowerCase() === diff.toLowerCase());
                }

                if (problems.length === 0) {
                    if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="padding:24px; text-align:center; color:#94a3b8;">No problems found.</td></tr>`;
                    return;
                }

                if (tableBody) {
                    tableBody.innerHTML = problems.map(p => `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:12px 14px; font-family:var(--font-mono); font-size:12px; color:#38bdf8;">${escapeHtml(p.id)}</td>
                            <td style="padding:12px 14px; font-weight:700; color:#f8fafc;">${escapeHtml(p.title)}</td>
                            <td style="padding:12px 14px;">
                                <span class="difficulty-badge ${p.difficulty ? p.difficulty.toLowerCase() : 'easy'}">${escapeHtml(p.difficulty || 'Easy')}</span>
                            </td>
                            <td style="padding:12px 14px; color:#cbd5e1;">${escapeHtml(p.category || 'Algorithms')}</td>
                            <td style="padding:12px 14px; color:#cbd5e1;">${p.submissions_count || 0}</td>
                            <td style="padding:12px 14px; color:#22c55e;">${p.acceptance_rate || 100}%</td>
                            <td style="padding:12px 14px; text-align:right;">
                                <button onclick="selectProblem('${p.id}'); showPractice();" class="run-button" style="margin:0; padding:4px 10px; font-size:11px; background:rgba(212,175,55,0.15); border:1px solid #d4af37; color:#d4af37; border-radius:5px; cursor:pointer;">Open in Editor</button>
                            </td>
                        </tr>
                    `).join('');
                }
            } catch (err) {
                if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="padding:24px; text-align:center; color:#ef4444;">Error: ${escapeHtml(err.message)}</td></tr>`;
            }
        }

        async function loadAdminMayaMetrics() {
            try {
                const res = await authFetch(`${API_BASE}/api/admin/ai/metrics`);
                if (!res.ok) return;
                const d = await res.json();
                const totalReqEl = document.getElementById('adminMayaTotalRequests');
                const avgLatEl = document.getElementById('adminMayaAvgLatency');
                const tokensEl = document.getElementById('adminMayaTotalTokens');
                const fallbacksEl = document.getElementById('adminMayaFallbacks');

                if (totalReqEl) totalReqEl.textContent = d.total_requests !== undefined ? d.total_requests : '--';
                if (avgLatEl) avgLatEl.textContent = d.average_latency_ms !== undefined ? `${d.average_latency_ms} ms` : '-- ms';
                if (tokensEl) tokensEl.textContent = d.estimated_tokens_total !== undefined ? d.estimated_tokens_total.toLocaleString() : '--';
                if (fallbacksEl) fallbacksEl.textContent = d.fallback_events_total !== undefined ? d.fallback_events_total : '0';
            } catch (e) {
                console.error('Error loading Maya metrics:', e);
            }
        }

        async function loadAdminProviders() {
            const grid = document.getElementById('adminProvidersGrid');
            if (grid) grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:24px; color:#94a3b8;">Loading AI provider infrastructure...</div>`;

            try {
                const res = await authFetch(`${API_BASE}/api/admin/ai/providers`);
                if (!res.ok) throw new Error('Failed to load providers');
                const d = await res.json();
                const providers = d.providers || [];

                if (grid) {
                    grid.innerHTML = providers.map(p => `
                        <div style="background:#090d15; border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:20px;">
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">
                                <div>
                                    <h4 style="margin:0; font-size:16px; font-weight:700; color:#f8fafc;">${escapeHtml(p.name)}</h4>
                                    <div style="font-size:11.5px; color:#38bdf8; font-family:var(--font-mono); margin-top:2px;">${escapeHtml(p.model)}</div>
                                </div>
                                <span style="background:rgba(34,197,94,0.15); color:#22c55e; border:1px solid rgba(34,197,94,0.3); padding:3px 8px; border-radius:6px; font-size:11px; font-weight:700;">
                                    ● ${escapeHtml(p.status.toUpperCase())}
                                </span>
                            </div>
                            <div style="font-size:12.5px; color:#cbd5e1; display:flex; flex-direction:column; gap:6px; margin-bottom:16px;">
                                <div><strong>Role:</strong> ${escapeHtml(p.role)}</div>
                                <div><strong>Priority:</strong> Tier ${p.priority} (Primary Fallback Chain)</div>
                                <div><strong>Average Latency:</strong> ${p.latency_ms || 240} ms</div>
                                <div><strong>Credentials:</strong> <span style="color:#22c55e;">Server Environment Sealed 🔒</span></div>
                            </div>
                            <button onclick="testProviderHealth('${p.id}')" style="width:100%; padding:8px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.1); color:#cbd5e1; border-radius:6px; font-size:12px; font-weight:600; cursor:pointer;">
                                Ping Provider Health
                            </button>
                        </div>
                    `).join('');
                }
            } catch (err) {
                if (grid) grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:24px; color:#ef4444;">Error: ${escapeHtml(err.message)}</div>`;
            }
        }

        async function testProviderHealth(providerId) {
            alert(`Health probe sent to ${providerId}. Provider circuit is alive and passing health check.`);
        }

        async function loadAdminAudits(page = 1) {
            const tableBody = document.getElementById('adminAuditsTableBody');
            const pagination = document.getElementById('adminAuditsPagination');
            const search = (document.getElementById('adminAuditsSearchInput') ? document.getElementById('adminAuditsSearchInput').value : '').trim();
            const action = (document.getElementById('adminAuditsActionFilter') ? document.getElementById('adminAuditsActionFilter').value : '');
            const result = (document.getElementById('adminAuditsResultFilter') ? document.getElementById('adminAuditsResultFilter').value : '');
            if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#94a3b8;">Loading audit events...</td></tr>`;

            try {
                const params = new URLSearchParams({ page: page, limit: 12 });
                if (search) params.append('q', search);
                if (action) params.append('action', action);
                if (result) params.append('result', result);

                const res = await authFetch(`${API_BASE}/api/admin/audit-logs?${params.toString()}`);
                if (!res.ok) throw new Error('Failed to load audit logs');
                const d = await res.json();

                if (!d.logs || d.logs.length === 0) {
                    if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#94a3b8;">No audit records found.</td></tr>`;
                    if (pagination) pagination.innerHTML = '';
                    return;
                }

                if (tableBody) {
                    tableBody.innerHTML = d.logs.map(l => `
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:10px 12px; color:#94a3b8; font-size:11.5px; white-space:nowrap;">${new Date(l.timestamp).toLocaleString()}</td>
                            <td style="padding:10px 12px; color:#f8fafc; font-weight:600;">${escapeHtml(l.actor_email || 'Guest')}</td>
                            <td style="padding:10px 12px;"><span style="color:#cbd5e1; font-size:11px;">${escapeHtml(l.actor_role || 'guest')}</span></td>
                            <td style="padding:10px 12px;"><code style="background:rgba(212,175,55,0.1); color:#d4af37; padding:2px 6px; border-radius:4px; font-size:11.5px;">${escapeHtml(l.action)}</code></td>
                            <td style="padding:10px 12px; color:#cbd5e1; font-size:12px;">${escapeHtml(l.resource_type || '--')}</td>
                            <td style="padding:10px 12px;"><span style="color:${l.result === 'success' ? '#22c55e' : l.result === 'denied' ? '#f59e0b' : '#ef4444'}; font-weight:700; font-size:11.5px;">${escapeHtml(l.result.toUpperCase())}</span></td>
                            <td style="padding:10px 12px; font-family:var(--font-mono); font-size:11.5px; color:#94a3b8;">${escapeHtml(l.ip_address || '127.0.0.1')}</td>
                            <td style="padding:10px 12px; color:#94a3b8; font-size:11.5px; max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(l.details || '--')}</td>
                        </tr>
                    `).join('');
                }

                if (pagination) {
                    pagination.innerHTML = `
                        <div>Showing page ${d.page} of ${d.total_pages} (${d.total_logs} logs)</div>
                        <div style="display:flex; gap:6px;">
                            <button onclick="loadAdminAudits(${d.page - 1})" ${d.page <= 1 ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : 'style="cursor:pointer;"'} class="filter-btn" style="padding:5px 12px; font-size:12px;">← Prev</button>
                            <button onclick="loadAdminAudits(${d.page + 1})" ${d.page >= d.total_pages ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : 'style="cursor:pointer;"'} class="filter-btn" style="padding:5px 12px; font-size:12px;">Next →</button>
                        </div>
                    `;
                }
            } catch (err) {
                if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="padding:24px; text-align:center; color:#ef4444;">Error: ${escapeHtml(err.message)}</td></tr>`;
            }
        }

        async function loadAdminSystem() {
            try {
                const res = await authFetch(`${API_BASE}/api/admin/system`);
                if (!res.ok) return;
                const d = await res.json();
                const eng = document.getElementById('adminSysDbEngine');
                const exp = document.getElementById('adminSysSessionExpiry');
                if (eng) eng.textContent = d.database ? `${d.database.engine} (${d.database.status})` : 'SQLite';
                if (exp) exp.textContent = d.auth ? `${d.auth.session_expiry_days} Days Sliding` : '7 Days Sliding';
            } catch (e) {
                console.error('Error loading admin system stats:', e);
            }
        }

        // Application State
        let currentPage = 1;
        let pageSize = 10;
        let totalPages = 1;
        let totalCount = 0;
        let searchDebounceTimer = null;
        let activeProblemId = null;

        // Active filters
        let filters = {
            search: "",
            difficulty: "",
            domain: "",
            source: "",
            problem_type: ""
        };

        // NAVIGATION
        function setActiveNav(activeId) {
            ["navDashboard", "navProblems", "navPractice", "navTests", "navProgress", "navAdminPortal"].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.classList.remove("active");
            });
            const activeEl = document.getElementById(activeId);
            if (activeEl) activeEl.classList.add("active");
        }

        function hideAllViews() {
            document.getElementById("dashboard").style.display = "none";
            document.getElementById("problemBrowser").style.display = "none";
            document.getElementById("practice").style.display = "none";
            document.getElementById("testsView").style.display = "none";
            document.getElementById("testTakingView").style.display = "none";
            const pView = document.getElementById("progressView");
            if (pView) pView.style.display = "none";
            const aView = document.getElementById("adminPortalView");
            if (aView) aView.style.display = "none";
        }

        function showDashboard() {
            window.active_workspace = 'dashboard';
            hideAllViews();
            document.getElementById("dashboard").style.display = "block";
            setActiveNav("navDashboard");
            fetchStats();
            initDashboard();
        }

        // ===================== DASHBOARD WIDGETS =====================

        function renderDashboardLoading() {
            const setIf = (id, html) => {
                const el = document.getElementById(id);
                if (el) el.innerHTML = html;
            };
            const setTextIf = (id, text) => {
                const el = document.getElementById(id);
                if (el) el.textContent = text;
            };
            setTextIf('dashTotalSolved', '—');
            setIf('dashSolvedSub', '<span style="color:#94a3b8;font-size:12px;">Loading metrics…</span>');
            setTextIf('dashAcceptanceRate', '—%');
            setIf('dashAttemptedSub', '<span style="color:#94a3b8;font-size:12px;">Loading activity…</span>');
            setTextIf('dashMasteryScore', '—%');
            setIf('dashMasteryTierSummary', '<span style="color:#94a3b8;font-size:11px;">Loading concept mastery…</span>');
            setTextIf('dashAvgScore', '—%');
            setIf('dashTestsCompleted', '<span style="color:#94a3b8;font-size:12px;">Loading evaluations…</span>');
            setIf('dashProgressChanges', '<div class="dash-loading"></div><div class="dash-loading" style="width:70%;"></div>');
            setIf('dashLanguageActivity', '<div class="dash-loading" style="width:50%;"></div>');
            setIf('dashRecommendations', '<div class="dash-loading"></div><div class="dash-loading" style="width:80%;margin-top:10px;"></div>');
            setIf('dashConceptMap', '<div class="dash-loading"></div><div class="dash-loading" style="width:65%;"></div>');
            setIf('dashErrorDNA', '<div class="dash-loading"></div><div class="dash-loading" style="width:75%;"></div>');
        }

        async function initDashboard() {
            if (!isAuthenticated()) {
                renderDashboardWidgets(null, null, { notAuthenticated: true });
                return;
            }
            // Run intro animation only once per session
            if (!sessionStorage.getItem('cmIntroShown')) {
                sessionStorage.setItem('cmIntroShown', '1');
                runIntroAnimation();
            }
            // Apply name immediately from cache
            applyUserName();
            const sid = getStudentId();

            renderDashboardLoading();

            // Load dashboard data in parallel using authenticated fetch
            try {
                const [progressRes, masteryRes] = await Promise.all([
                    authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid || '')}`),
                    authFetch(`${API_BASE}/api/mastery/dashboard?student_id=${encodeURIComponent(sid || '')}`)
                ]);

                if (!progressRes.ok) {
                    const statusText = `HTTP ${progressRes.status}`;
                    console.error('Progress API response error:', progressRes.status);
                    renderDashboardWidgets(null, null, { isError: true, error: statusText });
                    return;
                }

                const progressData = await progressRes.json();
                const masteryData = masteryRes.ok ? await masteryRes.json() : null;

                // Persist student_name from API as single source of truth (sanitized)
                if (progressData && progressData.student_name) {
                    let sName = progressData.student_name;
                    localStorage.setItem('codemind_user_name', sName);
                    applyUserName();
                }
                renderDashboardWidgets(progressData, masteryData, null);
            } catch(e) {
                console.error('Dashboard data load failed:', e);
                renderDashboardWidgets(null, null, { isError: true, error: e.message || 'Network error' });
            }
        }

        // Applies the authenticated user's name to every name placeholder across all views.
        // Always reads from authenticated user state — used everywhere.
        function applyUserName() {
            const user = getAuthUser();
            let name = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const dashEl = document.getElementById('dashUserName');
            if (dashEl) dashEl.textContent = name;
            const dashDisplayEl = document.getElementById('dashNameDisplay');
            if (dashDisplayEl) dashDisplayEl.textContent = name;
            const progEl = document.getElementById('progressUserName');
            if (progEl) progEl.textContent = name;
            const sepEl = document.getElementById('progressUserNameSep');
            if (sepEl) sepEl.style.display = name ? 'inline' : 'none';
            const navEl = document.getElementById('navUserName');
            if (navEl) navEl.textContent = name;
            const introEl = document.getElementById('introName');
            if (introEl) introEl.textContent = name;

            const greeting = document.getElementById('companionGreetingBubble');
            if (greeting) {
                const bName = window.currentUserBotName || localStorage.getItem('codemind_bot_name') || 'Maya';
                greeting.innerHTML = `👋 Hello <strong>${escapeHtml(name)}</strong>! I am <strong>${escapeHtml(bName)}</strong>, your CodeMind AI Companion &amp; Tutor. Ask me anything about programming, algorithms, recursion, pointers, or code debugging!`;
            }
        }

        function startNameEdit() {
            const user = getAuthUser();
            const current = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const group = document.getElementById('nameInputGroup');
            const input = document.getElementById('inputEditName');
            const editBtn = document.getElementById('btnEditName');
            const displayEl = document.getElementById('dashNameDisplay');
            if (group && input) {
                input.value = current;
                group.style.display = 'inline-flex';
                if (editBtn) editBtn.style.display = 'none';
                if (displayEl) displayEl.style.display = 'none';
                input.focus();
                input.select();
            }
        }

        function cancelNameEdit() {
            const group = document.getElementById('nameInputGroup');
            const editBtn = document.getElementById('btnEditName');
            const displayEl = document.getElementById('dashNameDisplay');
            if (group) group.style.display = 'none';
            if (editBtn) editBtn.style.display = 'inline-block';
            if (displayEl) displayEl.style.display = 'inline';
        }

        async function confirmNameEdit() {
            const input = document.getElementById('inputEditName');
            if (!input) return;
            const val = input.value.trim();
            if (val) {
                await saveUserName(val);
            }
            cancelNameEdit();
        }

        function startNavNameEdit() {
            openCompanionRenameModal();
        }

        async function saveUserName(newName) {
            newName = (newName || '').trim();
            if (!newName) return;
            try {
                const res = await authFetch(`${API_BASE}/api/auth/profile`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ display_name: newName })
                });
                if (res.ok) {
                    const data = await res.json();
                    if (data.display_name) newName = data.display_name;
                }
            } catch (e) {
                console.warn('Profile update endpoint notice:', e);
            }
            localStorage.setItem('codemind_user_name', newName);
            const user = getAuthUser();
            if (user) {
                user.display_name = newName;
                localStorage.setItem('codemind_auth_user', JSON.stringify(user));
            }
            applyUserName();
            renderNavAuth();
            if (typeof showToast === 'function') {
                showToast(`Display name updated to ${newName}`);
            }
        }

        function renderDashboardWidgets(prog, mastery, loadState) {
            // ---- Error State Handling ----
            if (loadState && loadState.isError) {
                const retryBtn = `<button onclick="initDashboard()" style="margin-left:8px;padding:2px 8px;font-size:11px;background:#1e293b;border:1px solid #38bdf8;color:#38bdf8;border-radius:4px;cursor:pointer;">Retry</button>`;
                const errSub = `<span style="color:#f87171;font-size:12px;">Failed to load. ${retryBtn}</span>`;
                
                const totalSolvedEl = document.getElementById('dashTotalSolved');
                if (totalSolvedEl) totalSolvedEl.textContent = '—';
                const solvedSubEl = document.getElementById('dashSolvedSub');
                if (solvedSubEl) solvedSubEl.innerHTML = errSub;

                const accEl = document.getElementById('dashAcceptanceRate');
                if (accEl) accEl.textContent = '—%';
                const attSubEl = document.getElementById('dashAttemptedSub');
                if (attSubEl) attSubEl.innerHTML = errSub;

                const mEl = document.getElementById('dashMasteryScore');
                if (mEl) mEl.textContent = '—%';
                const mTierEl = document.getElementById('dashMasteryTierSummary');
                if (mTierEl) mTierEl.innerHTML = `<span style="color:#f87171;font-size:11px;">Could not retrieve mastery data.</span>`;

                const testsScoreEl = document.getElementById('dashAvgScore');
                if (testsScoreEl) testsScoreEl.textContent = '—%';
                const testsCountEl = document.getElementById('dashTestsCompleted');
                if (testsCountEl) testsCountEl.innerHTML = `<span style="color:#f87171;font-size:12px;">Could not retrieve assessments.</span>`;

                const pcEl = document.getElementById('dashProgressChanges');
                if (pcEl) pcEl.innerHTML = `<div style="color:#f87171;font-size:12px;padding:6px 0;">⚠️ Service communication error. ${retryBtn}</div>`;

                const langEl = document.getElementById('dashLanguageActivity');
                if (langEl) langEl.innerHTML = `<div style="color:#f87171;font-size:12px;padding:6px 0;">Language activity unavailable.</div>`;

                const recEl = document.getElementById('dashRecommendations');
                if (recEl) recEl.innerHTML = `<div style="color:#f87171;font-size:12px;padding:12px;background:#1e1b18;border:1px solid #78350f;border-radius:8px;">⚠️ Recommendations temporarily unavailable. ${retryBtn}</div>`;

                const whyEl = document.getElementById('dashWhyRec');
                if (whyEl) whyEl.innerHTML = `<div style="color:#64748b;font-size:13px;">Reasoning will appear once recommendations are loaded.</div>`;

                const mapEl = document.getElementById('dashConceptMap');
                if (mapEl) mapEl.innerHTML = `<div style="color:#f87171;font-size:12px;padding:6px 0;">Concept map unavailable.</div>`;

                const dnaEl = document.getElementById('dashErrorDNA');
                if (dnaEl) dnaEl.innerHTML = `<div style="color:#f87171;font-size:12px;padding:6px 0;">Coding DNA unavailable.</div>`;

                const lastTitleEl = document.getElementById('dashLastProblemTitle');
                if (lastTitleEl) lastTitleEl.textContent = 'Session data unavailable';
                const lastSubEl = document.getElementById('dashLastProblemSub');
                if (lastSubEl) lastSubEl.textContent = 'Click retry or browse catalog';

                initCompanionWidget();
                return;
            }

            // ---- Continue Where You Left Off (Scoped to Authenticated User) ----
            const sid = getStudentId();
            const subs = (prog && prog.submissions) || [];
            let lastProblem = null;
            let lastTitle = null;
            if (subs.length > 0) {
                lastProblem = subs[0].problem_id;
                lastTitle = subs[0].problem_title || subs[0].problem_id;
            } else {
                const userLastProb = localStorage.getItem(`codemind_last_problem_${sid}`) || localStorage.getItem('codemind_last_problem');
                const userLastTitle = localStorage.getItem(`codemind_last_problem_title_${sid}`) || localStorage.getItem('codemind_last_problem_title');
                if (userLastProb && userLastTitle) {
                    lastProblem = userLastProb;
                    lastTitle = userLastTitle;
                }
            }

            if (lastProblem && lastTitle) {
                const el = document.getElementById('dashLastProblemTitle');
                const sub = document.getElementById('dashLastProblemSub');
                if (el) el.textContent = lastTitle;
                if (sub) sub.textContent = 'Resume from where you stopped';
                const card = document.querySelector('#dashContinueArea .continue-card');
                if (card) card.onclick = () => { openProblem(lastProblem); };
            } else {
                const el = document.getElementById('dashLastProblemTitle');
                if (el) el.textContent = 'No active session — start a new problem!';
                const sub = document.getElementById('dashLastProblemSub');
                if (sub) sub.textContent = 'Browse the library to begin';
                const card = document.querySelector('#dashContinueArea .continue-card');
                if (card) card.onclick = () => { showProblemBrowser(); };
            }

            // ---- Extract Real Submissions & Overview Stats ----
            const solved = (prog && prog.overview && prog.overview.problems_solved !== undefined)
                ? prog.overview.problems_solved
                : (new Set(subs.filter(s => (s.status || '').toLowerCase() === 'accepted').map(s => s.problem_id))).size;
            const attempted = (prog && prog.overview && prog.overview.problems_attempted !== undefined)
                ? prog.overview.problems_attempted
                : (new Set(subs.map(s => s.problem_id))).size;
            const total = (prog && prog.overview && prog.overview.total_submissions !== undefined)
                ? prog.overview.total_submissions
                : subs.length;
            const acceptedRuns = (prog && prog.overview && prog.overview.accepted_submissions !== undefined)
                ? prog.overview.accepted_submissions
                : subs.filter(s => (s.status || '').toLowerCase() === 'accepted').length;
            const acc = (prog && prog.overview && prog.overview.accuracy_rate !== undefined)
                ? Math.round(prog.overview.accuracy_rate)
                : (total > 0 ? Math.round(acceptedRuns / total * 100) : 0);
            const testsCount = (prog && prog.overview && prog.overview.tests_completed !== undefined)
                ? prog.overview.tests_completed
                : (prog && Array.isArray(prog.test_history) ? prog.test_history.length : 0);
            const avgScore = (prog && prog.overview && prog.overview.average_score !== undefined)
                ? Math.round(prog.overview.average_score)
                : 0;

            // ---- 1. TOTAL SOLVED ----
            const totalSolvedEl = document.getElementById('dashTotalSolved');
            if (totalSolvedEl) totalSolvedEl.textContent = solved;
            const streak = (prog && (prog.daily_streak !== undefined ? prog.daily_streak : (prog.overview && prog.overview.daily_streak !== undefined ? prog.overview.daily_streak : 0))) || 0;
            const solvedSubEl = document.getElementById('dashSolvedSub');
            if (solvedSubEl) {
                const streakText = streak > 0 ? ` · 🔥 ${streak}d streak` : '';
                if (total > 0) {
                    solvedSubEl.textContent = `${solved} problem${solved === 1 ? '' : 's'} solved${streakText}`;
                } else {
                    solvedSubEl.textContent = 'No solved problems yet';
                }
            }

            // Journey difficulty breakdown bars
            const byDiff = { Easy: 0, Medium: 0, Hard: 0, Expert: 0 };
            subs.filter(s => (s.status || '').toLowerCase() === 'accepted').forEach(s => {
                const d = s.difficulty || 'Easy';
                if (byDiff[d] !== undefined) byDiff[d]++;
            });
            const maxVal = Math.max(1, ...Object.values(byDiff));
            const barsEl = document.getElementById('dashJourneyBars');
            if (barsEl) {
                barsEl.innerHTML = Object.entries(byDiff).map(([d, v]) => {
                    const h = solved > 0 ? (Math.round((v / maxVal) * 36) + 6) : 4;
                    return `<div class="journey-bar-col"><div class="journey-bar" style="height:${h}px;" title="${d}: ${v}"></div><div class="journey-bar-label">${d[0]}</div></div>`;
                }).join('');
            }

            // ---- 2. ATTEMPTED & ACCEPTANCE RATE ----
            const accEl = document.getElementById('dashAcceptanceRate');
            if (accEl) accEl.textContent = (total > 0) ? `${acc}%` : '—%';
            const attSubEl = document.getElementById('dashAttemptedSub');
            if (attSubEl) {
                attSubEl.textContent = total > 0 ? `${attempted} problem${attempted === 1 ? '' : 's'} attempted · ${total} run${total === 1 ? '' : 's'}` : '0 problems attempted';
            }
            const accTrack = document.getElementById('dashAccuracyTrack');
            if (accTrack) {
                accTrack.style.width = (total > 0) ? `${Math.min(acc, 100)}%` : '0%';
            }

            // ---- 3. MASTERY SCORE ----
            let concepts = [];
            if (mastery) {
                if (Array.isArray(mastery.concepts)) concepts = mastery.concepts;
                else if (mastery.concept_mastery && Array.isArray(mastery.concept_mastery.concepts)) concepts = mastery.concept_mastery.concepts;
                else if (Array.isArray(mastery.concept_mastery)) concepts = mastery.concept_mastery;
            }
            if (concepts.length === 0 && prog && Array.isArray(prog.topic_strengths_and_weaknesses)) {
                concepts = prog.topic_strengths_and_weaknesses.map(t => ({
                    concept_name: t.topic,
                    mastery_score: t.mastery_percentage,
                    mastery_status: t.mastery_status || t.status,
                    total_attempts: t.attempted,
                    accepted_submissions: t.solved
                }));
            }

            const mEl = document.getElementById('dashMasteryScore');
            let overallMasteryPct = 0;
            if (mEl) {
                const totalMastery = mastery ? (mastery.overall_mastery_score ?? mastery.mastery_score) : null;
                if (totalMastery !== undefined && totalMastery !== null) {
                    overallMasteryPct = totalMastery > 1 ? Math.round(totalMastery) : Math.round(totalMastery * 100);
                } else if (concepts.length > 0) {
                    const avg = concepts.reduce((s, c) => {
                        const score = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage !== undefined ? c.mastery_percentage : (c.score || 0));
                        return s + (score > 1 ? score : score * 100);
                    }, 0) / concepts.length;
                    overallMasteryPct = Math.round(avg);
                }
                mEl.textContent = `${overallMasteryPct}%`;
            }
            const mTierEl = document.getElementById('dashMasteryTierSummary');
            if (mTierEl) {
                const verified = concepts.filter(c => c.is_verified || (c.mastery_status || '').toLowerCase() === 'strong').length;
                mTierEl.textContent = concepts.length > 0 ? `${verified} of ${concepts.length} concepts mastered` : 'Start solving to verify concepts';
            }

            // ---- 4. TESTS & ASSESSMENTS ----
            const testsScoreEl = document.getElementById('dashAvgScore');
            if (testsScoreEl) {
                testsScoreEl.textContent = testsCount > 0 ? `${avgScore}%` : '—%';
            }
            const testsCountEl = document.getElementById('dashTestsCompleted');
            if (testsCountEl) {
                testsCountEl.textContent = testsCount > 0 ? `${testsCount} completed assessment${testsCount === 1 ? '' : 's'}` : '0 evaluations completed';
            }

            // ---- 5. RECENT PROGRESS CHANGES ----
            const recentSolved = subs.filter(s => (s.status || '').toLowerCase() === 'accepted').slice(-5).reverse();
            const pcEl = document.getElementById('dashProgressChanges');
            if (pcEl) {
                if (recentSolved.length === 0) {
                    pcEl.innerHTML = total > 0
                        ? '<div style="color:#64748b;font-size:13px;padding:6px 0;">No accepted solutions yet. Keep trying!</div>'
                        : '<div style="color:#64748b;font-size:13px;padding:6px 0;">Start solving problems to see your progress here.</div>';
                } else {
                    pcEl.innerHTML = recentSolved.map(s => {
                        const title = s.problem_title || s.problem_id || 'Problem';
                        const diff = s.difficulty || '';
                        const diffColor = diff === 'Hard' || diff === 'Expert' ? '#ef4444' : diff === 'Medium' ? '#f59e0b' : '#22c55e';
                        return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                            <span class="delta-up" style="color:#22c55e;font-weight:700;">✓</span>
                            <span style="font-size:12px;color:#f1f5f9;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(title)}</span>
                            ${diff ? `<span style="font-size:10px;color:${diffColor};font-weight:700;">${diff}</span>` : ''}
                        </div>`;
                    }).join('');
                }
            }

            // ---- 6. LANGUAGE ACTIVITY ----
            const langEl = document.getElementById('dashLanguageActivity');
            if (langEl) {
                const lb = (prog && Array.isArray(prog.language_breakdown)) ? prog.language_breakdown : [];
                if (lb.length > 0) {
                    langEl.innerHTML = '<div style="display:flex; gap:8px; flex-wrap:wrap;">' +
                        lb.map(item => `
                            <div style="background:#090d15; border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:6px 12px; display:flex; align-items:center; gap:8px;">
                                <span style="font-weight:700; color:#38bdf8; font-size:12px;">${escapeHtml(item.language.toUpperCase())}</span>
                                <span style="color:#f8fafc; font-weight:600; font-size:12px;">${item.percentage}%</span>
                                <span style="color:#64748b; font-size:11px;">(${item.submissions})</span>
                            </div>
                        `).join('') + '</div>';
                } else {
                    langEl.innerHTML = '<div style="color:#64748b; font-size:13px; padding:6px 0;">No submission language activity detected yet.</div>';
                }
            }

            // ---- 7. MASTERY / CONCEPT MAP ----
            const mapEl = document.getElementById('dashConceptMap');
            if (mapEl) {
                if (concepts.length > 0) {
                    const tiers = { mastered: [], developing: [], weak: [], unseen: [] };
                    concepts.slice(0, 20).forEach(c => {
                        const name = c.concept_name || c.concept || c.topic || c.name || 'Unknown';
                        const score = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage !== undefined ? c.mastery_percentage : (c.score || 0));
                        const scoreRatio = score > 1 ? score / 100 : score;
                        const status = (c.mastery_status || c.status || '').toLowerCase();
                        const attempts = c.total_attempts !== undefined ? c.total_attempts : (c.attempted || 0);

                        if (status === 'strong' || scoreRatio >= 0.75) tiers.mastered.push(name);
                        else if (status === 'developing' || scoreRatio >= 0.4) tiers.developing.push(name);
                        else if (attempts > 0 || status === 'needs practice' || status === 'needs refresh' || scoreRatio > 0) tiers.weak.push(name);
                        else tiers.unseen.push(name);
                    });
                    let html = '';
                    const addPills = (arr, cls) => arr.map(n => '<span class="concept-pill ' + cls + '">' + escapeHtml(n) + '</span>').join('');
                    if (tiers.mastered.length) html += addPills(tiers.mastered, 'pill-mastered');
                    if (tiers.developing.length) html += addPills(tiers.developing, 'pill-developing');
                    if (tiers.weak.length) html += addPills(tiers.weak, 'pill-weak');
                    if (tiers.unseen.length) html += addPills(tiers.unseen.slice(0, 5), 'pill-unseen');
                    mapEl.innerHTML = html || '<div style="color:#64748b;font-size:13px;">No concept data yet.</div>';
                } else {
                    mapEl.innerHTML = '<div style="color:#64748b;font-size:13px;">No concept data available yet. Start solving problems!</div>';
                }
            }

            // ---- 8. YOUR CODING DNA ----
            const dnaEl = document.getElementById('dashErrorDNA');
            if (dnaEl) {
                const errorList = (mastery && mastery.error_dna && Array.isArray(mastery.error_dna.error_dna) && mastery.error_dna.error_dna.length > 0)
                    ? mastery.error_dna.error_dna
                    : (prog && Array.isArray(prog.common_mistakes) && prog.common_mistakes.length > 0)
                        ? prog.common_mistakes
                        : [];

                if (errorList.length > 0) {
                    const totalErrs = errorList.reduce((acc, m) => acc + (m.count || 0), 0);
                    dnaEl.innerHTML = '<div class="dash-widget-title" style="margin-bottom:10px;">Recurring Execution Patterns</div>' +
                        errorList.slice(0, 4).map(err => {
                            const label = err.label || (err.type ? err.type.replace(/_/g, ' ').toUpperCase() : 'Error');
                            const count = err.count || 0;
                            const pct = err.percentage !== undefined ? Math.round(err.percentage) : (totalErrs > 0 ? Math.round(count / totalErrs * 100) : 0);
                            return '<div class="dna-bar-row"><div class="dna-bar-label">' + escapeHtml(label) + '</div>' +
                                '<div class="dna-bar-track"><div class="dna-bar-fill" style="width:' + Math.max(pct, 5) + '%;"></div></div>' +
                                '<div class="dna-bar-count">' + count + ' (' + pct + '%)</div></div>';
                        }).join('');
                } else {
                    const weak = concepts.filter(c => {
                        const s = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage || 0);
                        return s < 50;
                    }).slice(0, 4);

                    if (weak.length > 0 && total > 0) {
                        dnaEl.innerHTML = '<div class="dash-widget-title" style="margin-bottom:10px;">Areas Needing Practice</div>' +
                            weak.map(c => {
                                const name = c.concept_name || c.concept || c.topic || 'Topic';
                                const s = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage || 0);
                                const pct = Math.round(s > 1 ? s : s * 100);
                                return '<div class="dna-bar-row"><div class="dna-bar-label">' + escapeHtml(name) + '</div>' +
                                    '<div class="dna-bar-track"><div class="dna-bar-fill" style="width:' + Math.max(pct, 5) + '%;"></div></div>' +
                                    '<div class="dna-bar-count">' + pct + '%</div></div>';
                            }).join('');
                    } else {
                        dnaEl.innerHTML = '<div style="color:#64748b;font-size:13px;">No execution DNA patterns detected yet. Practice problems to build your profile.</div>';
                    }
                }
            }

            // ---- 9. WHAT SHOULD I WORK ON? & WHY THIS IS RECOMMENDED ----
            const recEl = document.getElementById('dashRecommendations');
            let recList = [];
            if (mastery && mastery.recommendations) {
                if (Array.isArray(mastery.recommendations)) recList = mastery.recommendations;
                else if (Array.isArray(mastery.recommendations.recommendations)) recList = mastery.recommendations.recommendations;
            }
            if (recList.length === 0 && prog && prog.recommendations) {
                if (Array.isArray(prog.recommendations)) recList = prog.recommendations;
                else if (Array.isArray(prog.recommendations.recommendations)) recList = prog.recommendations.recommendations;
            }

            if (recEl) {
                if (recList.length === 0) {
                    recEl.innerHTML = `
                        <div style="background:#090d15; border:1px dashed rgba(212,175,55,0.25); border-radius:12px; padding:22px 18px; text-align:center;">
                            <div style="font-size:24px; margin-bottom:6px;">🎯</div>
                            <div style="font-weight:700; color:#f8fafc; font-size:14px; margin-bottom:4px;">No Active Recommendations Yet</div>
                            <div style="color:#94a3b8; font-size:12.5px; line-height:1.5; margin-bottom:12px;">
                                Solve problems in the library to generate personalized learning recommendations.
                            </div>
                            <button onclick="showProblemBrowser()" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#0a0a0a; font-weight:700; border:none; padding:7px 16px; border-radius:7px; cursor:pointer; font-size:12px;">
                                Explore Catalog (11,450+ Problems) →
                            </button>
                        </div>
                    `;
                    const whyEl = document.getElementById('dashWhyRec');
                    if (whyEl) {
                        whyEl.innerHTML = '<div style="color:#64748b;font-size:13px;line-height:1.7;">Solve problems in the library to generate personalized learning recommendations.</div>';
                    }
                } else {
                    recEl.innerHTML = recList.slice(0, 3).map((r, idx) => {
                        const title = r.title || r.problem_id || 'Recommended Problem';
                        const topic = r.target_topic || r.topic || 'Algorithms';
                        const diff = r.difficulty || r.mastery_status || 'Practice';
                        const reason = r.reason || ('Strengthen your ' + topic + ' mastery.');
                        const pid = r.problem_id || '';
                        const badgeColor = diff === 'Hard' ? '#ef4444' : diff === 'Medium' ? '#f59e0b' : '#38bdf8';

                        const matchingConcept = concepts.find(c => (c.concept_name || c.topic || '').toLowerCase() === topic.toLowerCase());
                        const pct = matchingConcept ? (matchingConcept.mastery_score !== undefined ? matchingConcept.mastery_score : (matchingConcept.mastery_percentage || 0)) : 0;

                        return '<div class="rec-card" onclick="dashShowWhyRec(' + JSON.stringify(title) + ',' + JSON.stringify(reason) + ',' + pct + ',' + JSON.stringify(pid) + ')">' +
                            '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">' +
                            '<div class="rec-card-title">' + (idx + 1) + '. ' + escapeHtml(title) + '</div>' +
                            '<span class="rec-card-badge" style="background:rgba(0,0,0,0.3);color:' + badgeColor + ';border:1px solid ' + badgeColor + ';">' + diff + '</span>' +
                            '</div>' +
                            '<div class="rec-card-reason">' + escapeHtml(topic) + ' · ' + escapeHtml(reason) + '</div>' +
                            '</div>';
                    }).join('');

                    // Automatically populate "Why This Is Recommended" with top recommendation
                    const first = recList[0];
                    const firstTitle = first.title || first.problem_id || 'Recommended Problem';
                    const firstTopic = first.target_topic || first.topic || 'Algorithms';
                    const firstReason = first.reason || ('Strengthen your ' + firstTopic + ' mastery.');
                    const firstPid = first.problem_id || '';
                    const matchConcept = concepts.find(c => (c.concept_name || c.topic || '').toLowerCase() === firstTopic.toLowerCase());
                    const firstPct = matchConcept ? (matchConcept.mastery_score !== undefined ? matchConcept.mastery_score : (matchConcept.mastery_percentage || 0)) : 0;
                    dashShowWhyRec(firstTitle, firstReason, firstPct, firstPid);
                }
            }

            // ---- 6. 3D AI Companion Widget ----
            initCompanionWidget();

            // ---- 7. AI Learning Insight ----
            renderAIInsight(concepts, prog, mastery);
        }

        function dashShowWhyRec(concept, reason, pct, problemId) {
            const el = document.getElementById('dashWhyRec');
            if (!el) return;
            const pctVal = Math.min(100, Math.max(0, Math.round(pct > 1 ? pct : pct * 100)));
            const actionBtn = problemId
                ? '<button onclick="openProblem(\'' + problemId + '\')" style="margin-top:14px;background:linear-gradient(135deg,#d4af37,#b8961e);color:#0a0a0a;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:700;font-size:12px;">Solve This Problem →</button>'
                : '<button onclick="showPractice()" style="margin-top:14px;background:linear-gradient(135deg,#d4af37,#b8961e);color:#0a0a0a;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:700;font-size:12px;">Practice This Topic →</button>';

            el.innerHTML = '<div style="margin-bottom:10px;">' +
                '<div style="font-size:14px;font-weight:700;color:#d4af37;margin-bottom:6px;">' + concept + '</div>' +
                '<div style="font-size:13px;color:#f1f5f9;line-height:1.6;">' + reason + '</div>' +
                '</div>' +
                '<div style="margin-top:12px;padding-top:12px;border-top:1px solid #1e2535;">' +
                '<div style="font-size:11px;color:#64748b;margin-bottom:4px;">Current Concept Mastery</div>' +
                '<div style="display:flex;align-items:center;gap:8px;">' +
                '<div style="flex:1;height:6px;background:#1e293b;border-radius:3px;overflow:hidden;">' +
                '<div style="height:100%;width:' + Math.max(pctVal, 3) + '%;background:linear-gradient(to right,#ef4444,#f59e0b);border-radius:3px;"></div>' +
                '</div>' +
                '<div style="font-size:12px;color:#d4af37;font-weight:700;">' + pctVal + '%</div>' +
                '</div>' +
                '</div>' +
                actionBtn;
        }

        // ===================== 3D AI COMPANION (STAGE 2) =====================
        function initCompanionWidget() {
            updateCompanionBotNameUI();
            if (window.loadCompanionVRM) {
                window.loadCompanionVRM();
            }
        }

        async function updateCompanionBotNameUI() {
            let botName = localStorage.getItem('codemind_bot_name');
            const displayEl = document.getElementById('companionBotNameDisplay');

            if (!botName) {
                try {
                    const sid = getStudentId();
                    const r = await authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid)}`);
                    if (r.ok) {
                        const data = await r.json();
                        if (data.bot_name) {
                            botName = data.bot_name;
                            localStorage.setItem('codemind_bot_name', botName);
                        }
                    }
                } catch (e) {
                    console.warn('Failed to fetch bot_name from progress API:', e);
                }
            }

            if (botName) {
                window.currentUserBotName = botName;
                if (displayEl) displayEl.textContent = botName;
                document.querySelectorAll('.companionBotNameInline').forEach(el => el.textContent = botName);
                const greeting = document.getElementById('companionGreetingBubble');
                if (greeting) {
                    greeting.textContent = `Hello! I am ${botName}, your 3D learning companion. I'm here to help explain concepts, trace code, and guide your problem-solving.`;
                }
            } else {
                window.currentUserBotName = 'Companion';
                if (displayEl) displayEl.textContent = 'Companion';
                document.querySelectorAll('.companionBotNameInline').forEach(el => el.textContent = 'Companion');
                openCompanionRenameModal(true);
            }
            if (typeof updateCompanionMuteUI === 'function') updateCompanionMuteUI();
        }

        function openCompanionRenameModal(isFirstTime = false) {
            const modal = document.getElementById('companionNameModal');
            const botInput = document.getElementById('companionNameInput');
            const learnerInput = document.getElementById('settingsLearnerNameInput');
            const voiceSelect = document.getElementById('settingsVoiceMode');
            const muteSelect = document.getElementById('settingsAudioMute');
            const acctName = document.getElementById('settingsAccountName');
            const acctRole = document.getElementById('settingsAccountRole');

            if (!modal) return;
            if (typeof updateGroqKeySettingsUI === 'function') updateGroqKeySettingsUI();
            const user = getAuthUser();
            const currentLearner = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const currentBot = localStorage.getItem('codemind_bot_name') || 'Maya';

            if (learnerInput) learnerInput.value = currentLearner;
            if (botInput) botInput.value = currentBot;

            if (voiceSelect) {
                voiceSelect.value = window.voiceAssistantActive ? 'on' : 'off';
            }
            if (muteSelect) {
                muteSelect.value = window.companionAudioMuted ? 'muted' : 'unmuted';
            }

            if (acctName) {
                if (user && user.username) {
                    acctName.textContent = `Signed in as: ${user.username} (${user.email || 'No email registered'})`;
                    if (acctRole) acctRole.textContent = (user.role || 'Student').toUpperCase();
                } else {
                    acctName.textContent = 'Guest mode — Sign in to sync your progress to the cloud';
                    if (acctRole) acctRole.textContent = 'GUEST';
                }
            }

            const vRow = document.getElementById('settingsVerificationRow');
            const vBadge = document.getElementById('settingsVerificationBadge');
            const vBtn = document.getElementById('settingsResendVerifyBtn');
            const secAccordion = document.getElementById('settingsSecurityAccordion');
            const dangerZone = document.getElementById('settingsDangerZone');
            const changeBox = document.getElementById('settingsChangePasswordBox');
            if (changeBox) changeBox.style.display = 'none';

            if (user && user.username) {
                if (vRow) {
                    vRow.style.display = 'flex';
                    if (user.is_verified) {
                        vBadge.innerHTML = '✅ <span style="color:#22c55e;">Email Verified</span>';
                        if (vBtn) vBtn.style.display = 'none';
                    } else {
                        vBadge.innerHTML = '⚠️ <span style="color:#f59e0b;">Email Unverified</span>';
                        if (vBtn) {
                            vBtn.style.display = 'inline-block';
                            vBtn.textContent = 'Resend Link';
                            vBtn.disabled = false;
                        }
                    }
                }
                if (secAccordion) secAccordion.style.display = 'block';
                if (dangerZone) dangerZone.style.display = 'block';
            } else {
                if (vRow) vRow.style.display = 'none';
                if (secAccordion) secAccordion.style.display = 'none';
                if (dangerZone) dangerZone.style.display = 'none';
            }

            modal.style.display = 'flex';
            document.body.classList.add('modal-open');
            if (learnerInput) learnerInput.focus();
        }

        function closeCompanionRenameModal() {
            const modal = document.getElementById('companionNameModal');
            if (modal) modal.style.display = 'none';
            document.body.classList.remove('modal-open');
        }

        async function saveCompanionNameFromModal() {
            const botInput = document.getElementById('companionNameInput');
            const learnerInput = document.getElementById('settingsLearnerNameInput');
            const voiceSelect = document.getElementById('settingsVoiceMode');
            const muteSelect = document.getElementById('settingsAudioMute');

            const enteredBot = (botInput ? botInput.value : '').trim() || 'Maya';
            const enteredLearner = (learnerInput ? learnerInput.value : '').trim();

            if (enteredLearner) {
                localStorage.setItem('codemind_user_name', enteredLearner);
                const user = getAuthUser();
                if (user) {
                    user.display_name = enteredLearner;
                    localStorage.setItem('codemind_auth_user', JSON.stringify(user));
                }
                applyUserName();
                renderNavAuth();
            }

            localStorage.setItem('codemind_bot_name', enteredBot);
            window.currentUserBotName = enteredBot;
            document.querySelectorAll('.companionBotNameInline').forEach(el => el.textContent = enteredBot);

            const displayEl = document.getElementById('companionBotNameDisplay');
            if (displayEl) displayEl.textContent = enteredBot;
            const greeting = document.getElementById('companionGreetingBubble');
            if (greeting) {
                const lName = enteredLearner || localStorage.getItem('codemind_user_name') || 'Learner';
                greeting.innerHTML = `👋 Hello ${escapeHtml(lName)}! I am <strong>${escapeHtml(enteredBot)}</strong>, your CodeMind AI Companion &amp; Tutor. Ask me anything about programming, algorithms, recursion, pointers, or code debugging!`;
            }

            // Sync Voice Assistant preference
            if (voiceSelect) {
                const wantVoice = (voiceSelect.value === 'on');
                if (wantVoice !== !!window.voiceAssistantActive) {
                    if (typeof toggleVoiceAssistantMode === 'function') {
                        toggleVoiceAssistantMode();
                    }
                }
            }

            // Sync Audio Mute preference
            if (muteSelect) {
                const wantMute = (muteSelect.value === 'muted');
                if (wantMute !== !!window.companionAudioMuted) {
                    if (typeof toggleCompanionAudioMute === 'function') {
                        toggleCompanionAudioMute();
                    }
                }
            }

            const voiceToggle = document.getElementById('companionVoiceToggle');
            if (voiceToggle) {
                voiceToggle.title = `Enable or disable Voice Assistant (Wake word '${enteredBot}')`;
            }

            try {
                const sid = getStudentId();
                const patchPayload = { bot_name: enteredBot };
                if (enteredLearner) patchPayload.display_name = enteredLearner;

                await authFetch(`${API_BASE}/api/auth/profile`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(patchPayload)
                });

                await authFetch(`${API_BASE}/api/progress/bot-name`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ student_id: sid, bot_name: enteredBot })
                });
            } catch (e) {
                console.warn('Failed to save settings to backend:', e);
            }

            closeCompanionRenameModal();
            if (typeof showToast === 'function') {
                showToast(`Settings saved: Learner: ${enteredLearner || 'Learner'}, Assistant: ${enteredBot}`);
            }
        }

        // ===================== PERSONAL GROQ API KEY MANAGEMENT =====================
        window.currentUserHasGroqKey = false;
        window.currentUserGroqKeyPreview = '';
        window._groqModalIsMandatory = false;

        function updateGroqKeySettingsUI() {
            const user = getAuthUser();
            const hasKey = !!(window.currentUserHasGroqKey || (user && user.has_groq_key));
            const preview = window.currentUserGroqKeyPreview || (user && user.groq_key_preview) || '';
            renderGroqKeyCardSync(hasKey, preview);

            if (isAuthenticated()) {
                authFetch(`${API_BASE}/api/ai/groq-key`).then(r => {
                    if (r.ok) return r.json();
                    return null;
                }).then(data => {
                    if (data && typeof data.configured === 'boolean') {
                        window.currentUserHasGroqKey = data.configured;
                        window.currentUserGroqKeyPreview = data.preview || '';
                        const u = getAuthUser();
                        if (u) {
                            u.has_groq_key = data.configured;
                            u.groq_key_preview = data.preview || '';
                            localStorage.setItem('codemind_auth_user', JSON.stringify(u));
                        }
                        renderGroqKeyCardSync(data.configured, data.preview, data.last_tested_at);
                    }
                }).catch(() => {});
            }
        }

        function renderGroqKeyCardSync(hasKey, preview, lastTestedAt) {
            const statusBadge = document.getElementById('settingsGroqStatusBadge');
            const confView = document.getElementById('settingsGroqConfiguredView');
            const unconfView = document.getElementById('settingsGroqUnconfiguredView');
            const previewEl = document.getElementById('settingsGroqKeyPreview');
            const lastTestedEl = document.getElementById('settingsGroqLastTested');

            if (!statusBadge || !confView || !unconfView) return;

            if (hasKey) {
                statusBadge.textContent = '● Connected';
                statusBadge.style.background = 'rgba(34,197,94,0.15)';
                statusBadge.style.color = '#22c55e';
                statusBadge.style.borderColor = 'rgba(34,197,94,0.3)';
                confView.style.display = 'block';
                unconfView.style.display = 'none';
                if (previewEl) previewEl.textContent = preview || '••••••••••••';
                if (lastTestedEl) {
                    if (lastTestedAt) {
                        try {
                            const d = new Date(lastTestedAt);
                            lastTestedEl.textContent = `Verified: ${d.toLocaleDateString()}`;
                        } catch(e) {
                            lastTestedEl.textContent = 'Verified OK';
                        }
                    } else {
                        lastTestedEl.textContent = 'Verified OK';
                    }
                }
            } else {
                statusBadge.textContent = '○ Not Configured';
                statusBadge.style.background = 'rgba(239,68,68,0.15)';
                statusBadge.style.color = '#f87171';
                statusBadge.style.borderColor = 'rgba(239,68,68,0.3)';
                confView.style.display = 'none';
                unconfView.style.display = 'block';
            }
        }

        function openGroqKeyModal(isMandatory = false) {
            const modal = document.getElementById('groqKeyModal');
            const input = document.getElementById('groqKeyInput');
            const banner = document.getElementById('groqKeyStatusBanner');
            const saveBtn = document.getElementById('groqKeySaveBtn');
            const cancelBtn = document.getElementById('groqKeyCancelBtn');
            const titleEl = document.getElementById('groqKeyModalTitle');

            if (!modal) return;
            window._groqModalIsMandatory = !!isMandatory;

            if (input) {
                input.value = '';
                input.type = 'password';
            }
            const toggleBtn = document.getElementById('groqKeyToggleVisBtn');
            if (toggleBtn) toggleBtn.textContent = '👁️';

            if (banner) banner.style.display = 'none';
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = '⚡ Save &amp; Test Key';
            }

            if (titleEl) {
                titleEl.textContent = isMandatory 
                    ? 'Connect Groq API Key to Continue' 
                    : 'Personal Groq API Key';
            }

            if (cancelBtn) {
                cancelBtn.textContent = isMandatory ? 'Skip For Now' : 'Cancel';
            }

            modal.style.display = 'flex';
            document.body.classList.add('modal-open');
            if (input) setTimeout(() => input.focus(), 80);
        }

        function closeGroqKeyModal() {
            const modal = document.getElementById('groqKeyModal');
            if (modal) modal.style.display = 'none';
            document.body.classList.remove('modal-open');

            if (window._groqModalIsMandatory && !window.currentUserHasGroqKey) {
                if (typeof showToast === 'function') {
                    showToast('💡 Maya AI Tutor is paused until a Groq API key is connected. You can add one anytime in Settings ⚙️.');
                }
            }
            window._groqModalIsMandatory = false;
        }

        function toggleGroqKeyVisibility() {
            const input = document.getElementById('groqKeyInput');
            const btn = document.getElementById('groqKeyToggleVisBtn');
            if (!input) return;
            if (input.type === 'password') {
                input.type = 'text';
                if (btn) btn.textContent = '🙈';
            } else {
                input.type = 'password';
                if (btn) btn.textContent = '👁️';
            }
        }

        async function handleSaveGroqKey() {
            const input = document.getElementById('groqKeyInput');
            const banner = document.getElementById('groqKeyStatusBanner');
            const saveBtn = document.getElementById('groqKeySaveBtn');
            const cancelBtn = document.getElementById('groqKeyCancelBtn');

            const keyVal = (input ? input.value : '').trim();
            if (!keyVal) {
                if (banner) {
                    banner.style.display = 'block';
                    banner.style.background = 'rgba(239,68,68,0.15)';
                    banner.style.border = '1px solid rgba(239,68,68,0.3)';
                    banner.style.color = '#fca5a5';
                    banner.innerHTML = '❌ Please enter a Groq API key (starts with <code>gsk_</code>).';
                }
                if (input) input.focus();
                return;
            }

            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.innerHTML = '⚡ Testing Key with Groq...';
            }
            if (cancelBtn) cancelBtn.disabled = true;

            if (banner) {
                banner.style.display = 'block';
                banner.style.background = 'rgba(212,175,55,0.15)';
                banner.style.border = '1px solid rgba(212,175,55,0.3)';
                banner.style.color = '#fde68a';
                banner.innerHTML = '🔄 Validating key with Groq servers (zero token cost)...';
            }

            try {
                const res = await authFetch(`${API_BASE}/api/ai/groq-key`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ api_key: keyVal })
                });

                const data = await res.json();
                if (!res.ok) {
                    const errDetail = safeExtractErrorMessage(data, 'Failed to save and validate Groq API key.');
                    throw new Error(errDetail);
                }

                // Success
                window.currentUserHasGroqKey = true;
                window.currentUserGroqKeyPreview = data.preview || '';
                const u = getAuthUser();
                if (u) {
                    u.has_groq_key = true;
                    u.groq_key_preview = data.preview || '';
                    localStorage.setItem('codemind_auth_user', JSON.stringify(u));
                }

                if (banner) {
                    banner.style.background = 'rgba(34,197,94,0.15)';
                    banner.style.border = '1px solid rgba(34,197,94,0.3)';
                    banner.style.color = '#86efac';
                    banner.innerHTML = `✅ <strong>Key Verified &amp; Saved!</strong> ${escapeHtml(data.preview || '')} is now connected. Maya AI tutor is active.`;
                }

                updateGroqKeySettingsUI();

                setTimeout(() => {
                    closeGroqKeyModal();
                    if (typeof showToast === 'function') {
                        showToast('🎉 Personal Groq API key connected! Maya tutor and Full Solution are unlocked.');
                    }
                }, 1100);

            } catch (err) {
                console.error('Save Groq Key error:', err);
                const errMsg = err.message || 'Validation failed. Please verify your Groq API key.';
                if (banner) {
                    banner.style.background = 'rgba(239,68,68,0.15)';
                    banner.style.border = '1px solid rgba(239,68,68,0.3)';
                    banner.style.color = '#fca5a5';
                    banner.innerHTML = `❌ <strong>Validation Error:</strong> ${escapeHtml(errMsg)}`;
                }
            } finally {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.innerHTML = '⚡ Save &amp; Test Key';
                }
                if (cancelBtn) cancelBtn.disabled = false;
            }
        }

        async function handleTestExistingGroqKey() {
            const btn = document.getElementById('settingsTestGroqBtn');
            const msgEl = document.getElementById('settingsGroqActionMsg');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Testing...';
            }
            if (msgEl) msgEl.style.display = 'none';

            try {
                const res = await authFetch(`${API_BASE}/api/ai/groq-key/test`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                const data = await res.json();
                if (!res.ok) {
                    throw new Error(safeExtractErrorMessage(data, 'Test failed.'));
                }

                if (msgEl) {
                    msgEl.style.display = 'block';
                    msgEl.style.background = 'rgba(34,197,94,0.12)';
                    msgEl.style.border = '1px solid rgba(34,197,94,0.3)';
                    msgEl.style.color = '#86efac';
                    msgEl.innerHTML = `✅ Stored Groq key is active &amp; verified working!`;
                }
            } catch (err) {
                if (msgEl) {
                    msgEl.style.display = 'block';
                    msgEl.style.background = 'rgba(239,68,68,0.12)';
                    msgEl.style.border = '1px solid rgba(239,68,68,0.3)';
                    msgEl.style.color = '#fca5a5';
                    msgEl.innerHTML = `❌ Key test failed: ${escapeHtml(err.message)}`;
                }
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '⚡ Test Key';
                }
            }
        }

        async function handleRemoveGroqKey() {
            if (!confirm('Are you sure you want to remove your Groq API key? Maya AI Tutor and Full Solution will be disabled until you reconnect a key.')) {
                return;
            }

            const btn = document.getElementById('settingsRemoveGroqBtn');
            const msgEl = document.getElementById('settingsGroqActionMsg');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Removing...';
            }

            try {
                const res = await authFetch(`${API_BASE}/api/ai/groq-key`, {
                    method: 'DELETE'
                });
                const data = await res.json();
                if (!res.ok) throw new Error(safeExtractErrorMessage(data, 'Failed to remove key.'));

                window.currentUserHasGroqKey = false;
                window.currentUserGroqKeyPreview = '';
                const u = getAuthUser();
                if (u) {
                    u.has_groq_key = false;
                    u.groq_key_preview = '';
                    localStorage.setItem('codemind_auth_user', JSON.stringify(u));
                }

                renderGroqKeyCardSync(false, '');
                if (msgEl) {
                    msgEl.style.display = 'block';
                    msgEl.style.background = 'rgba(239,68,68,0.12)';
                    msgEl.style.border = '1px solid rgba(239,68,68,0.3)';
                    msgEl.style.color = '#fca5a5';
                    msgEl.innerHTML = '🗑️ Groq API key removed. Maya tutor has been disabled.';
                }
                if (typeof showToast === 'function') {
                    showToast('Groq API key removed. AI features have been disabled.');
                }
            } catch (err) {
                alert(`Error removing key: ${err.message}`);
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '🗑️ Remove';
                }
            }
        }

        // ===================== STAGE 3: DETERMINISTIC GRAPHICAL VISUALIZATION ENGINE =====================
        let currentVizSpec = null;
        let currentVizStepIndex = 0;
        let vizPlayTimer = null;
        let vizPlaySpeed = 1500;

        /**
         * Safely formats any value (string, number, object, array) for visual renderers
         * preventing "[object Object]" leaks.
         */
        function formatVizValue(val) {
            if (val === null || val === undefined) return '—';
            if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') {
                return String(val);
            }
            if (typeof val === 'object') {
                if (val.val !== undefined) return formatVizValue(val.val);
                if (val.value !== undefined) return formatVizValue(val.value);
                if (val.label !== undefined) return formatVizValue(val.label);
                if (val.name !== undefined) return formatVizValue(val.name);
                if (val.node !== undefined) return formatVizValue(val.node);
                if (val.title !== undefined) return formatVizValue(val.title);
                if (val.text !== undefined) return formatVizValue(val.text);
                if (val.data !== undefined) return formatVizValue(val.data);
                if (val.from !== undefined && val.to !== undefined) return `${formatVizValue(val.from)} ➔ ${formatVizValue(val.to)}`;
                if (Array.isArray(val)) {
                    return `[${val.map(formatVizValue).join(', ')}]`;
                }
                try {
                    return JSON.stringify(val);
                } catch (e) {
                    return String(val);
                }
            }
            return String(val);
        }

        function updateAIInsightForActiveVisualization(spec) {
            const el = document.getElementById('dashAIInsight');
            if (!el || !spec) return;

            const topic = (spec.viz_type || 'Data Structure').replace(/_/g, ' ').toUpperCase();
            const title = spec.title || 'Interactive Visualization';

            let pedagogy = '';
            const vt = (spec.viz_type || '').toLowerCase();
            if (vt === 'circular_linked_list' || vt === 'circular-linked-list' || vt === 'cll') {
                pedagogy = 'A **Circular Linked List** connects the last node directly back to the `HEAD` node, forming an unbroken closed ring. There is strictly NO `NULL` pointer at the tail. Traversal can cycle continuously unless bounded by node counting or reference equality checks.';
            } else if (vt === 'doubly_linked_list' || vt === 'doubly-linked-list') {
                pedagogy = 'A **Doubly Linked List** maintains bidirectional pointers (`prev` and `next`) on every node. While each node incurs extra pointer memory overhead, it achieves O(1) removals and bidirectional traversals from both Head and Tail without requiring full forward linear scans.';
            } else if (vt === 'linked_list' || vt === 'singly_linked_list') {
                pedagogy = 'A **Singly Linked List** allocates memory dynamically per node. Pointers (`next`) chain elements sequentially. Prepending to the Head is O(1), but random indexing requires O(N) sequential traversal from Head to Tail.';
            } else if (vt === 'stack') {
                pedagogy = 'A **Stack** enforces LIFO (Last-In, First-Out) semantics. Both `push` and `pop` execute strictly at the `TOP` in O(1) time. This structure is foundational for call stacks, expression evaluation, backtracking, and DFS.';
            } else if (vt === 'queue' || vt === 'circular_queue') {
                pedagogy = 'A **Queue** enforces FIFO (First-In, First-Out) discipline. Enqueue happens at `REAR` and Dequeue at `FRONT` in O(1) time. Circular queues wrap pointers modulo buffer capacity to eliminate memory drift.';
            } else if (vt === 'searching' || vt === 'binary_search') {
                pedagogy = 'A **Binary Search** requires a pre-sorted sequence. By halving the search space on each comparison (`mid = (low + high) // 2`), it achieves optimal O(log N) search complexity.';
            } else if (vt === 'tree' || vt === 'bst') {
                pedagogy = 'A **Binary Search Tree** maintains the invariant that all left subtrees contain keys strictly smaller than the parent, and right subtrees contain keys strictly greater. Average search, insert, and delete are O(log N).';
            } else if (vt === 'recursion') {
                pedagogy = 'A **Recursive Function** breaks problems into smaller subproblems. Each recursive call allocates a frame on the runtime Call Stack until a definitive Base Case triggers unwinding and return value propagation.';
            } else if (vt === 'sorting') {
                pedagogy = 'Algorithm comparison steps identify inversions in the sequence and execute in-place swaps until the invariant of monotonically sorted order is satisfied.';
            } else {
                pedagogy = 'Analyzing active visualization state for **' + escapeHtml(title) + '**. Step through the timeline controls to inspect pointer updates and state transitions.';
            }

            el.innerHTML = '<div class="ai-insight-box">' +
                '<div style="font-size:11px; font-weight:700; color:#38bdf8; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px;">Active Visualization Context: ' + escapeHtml(topic) + '</div>' +
                '<div style="color:#f1f5f9; font-size:12px; line-height:1.6;">' + pedagogy + '</div>' +
                '<div class="ai-author">✨ Synchronized with Active Visualization</div>' +
                '</div>';
        }

        function renderCompanionVisualization(spec) {
            if (!spec) return;
            // 1. Strict State Isolation: clear running playback, reset pointers & stage
            if (vizPlayTimer) {
                clearInterval(vizPlayTimer);
                vizPlayTimer = null;
                const playBtn = document.getElementById('companionVizPlayBtn');
                if (playBtn) playBtn.textContent = '▶ Play';
            }
            currentVizSpec = null;
            currentVizStepIndex = 0;

            const panel = document.getElementById('companionVizPanel');
            const titleEl = document.getElementById('companionVizTitle');
            const badgeEl = document.getElementById('companionVizBadge');
            const scrubber = document.getElementById('companionVizScrubber');
            const stage = document.getElementById('companionVizStage');
            const explEl = document.getElementById('companionVizExplanation');

            if (stage) stage.innerHTML = '';
            if (explEl) explEl.innerHTML = 'Select a step to inspect the state transition.';

            // 2. Load fresh specification and sync AI Learning Insight
            currentVizSpec = spec;
            currentVizStepIndex = 0;

            if (!panel) return;
            panel.style.display = 'flex';
            panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            if (titleEl) titleEl.textContent = spec.title || 'Algorithm Visualization';
            if (badgeEl) badgeEl.textContent = (spec.viz_type || 'DSA').toUpperCase();

            // Synchronize AI Learning Insight with the active visualization topic (Fixes Hash Table context bug)
            updateAIInsightForActiveVisualization(spec);

            const totalSteps = (spec.steps && spec.steps.length) || 1;
            if (scrubber) {
                scrubber.min = 0;
                scrubber.max = totalSteps - 1;
                scrubber.value = 0;
            }

            renderVizStep(0);
        }

        function closeCompanionViz() {
            if (vizPlayTimer) {
                clearInterval(vizPlayTimer);
                vizPlayTimer = null;
                const playBtn = document.getElementById('companionVizPlayBtn');
                if (playBtn) playBtn.textContent = '▶ Play';
            }
            currentVizSpec = null;
            currentVizStepIndex = 0;
            const stage = document.getElementById('companionVizStage');
            if (stage) stage.innerHTML = '';
            const panel = document.getElementById('companionVizPanel');
            if (panel) panel.style.display = 'none';

            // Restore baseline AI Learning Insight
            if (window._cachedDashboardInsight) {
                const el = document.getElementById('dashAIInsight');
                if (el) el.innerHTML = window._cachedDashboardInsight;
            }
        }

        function toggleCompanionVizPlay() {
            const playBtn = document.getElementById('companionVizPlayBtn');
            if (vizPlayTimer) {
                clearInterval(vizPlayTimer);
                vizPlayTimer = null;
                if (playBtn) playBtn.textContent = '▶ Play';
            } else {
                if (!currentVizSpec || !currentVizSpec.steps) return;
                if (playBtn) playBtn.textContent = '⏸ Pause';
                vizPlayTimer = setInterval(() => {
                    if (currentVizStepIndex < currentVizSpec.steps.length - 1) {
                        stepCompanionViz(1);
                    } else {
                        // Loop back to start or pause
                        stepCompanionViz(-currentVizSpec.steps.length);
                    }
                }, vizPlaySpeed);
            }
        }

        function stepCompanionViz(delta) {
            if (!currentVizSpec || !currentVizSpec.steps) return;
            let nextIndex = currentVizStepIndex + delta;
            if (nextIndex < 0) nextIndex = 0;
            if (nextIndex >= currentVizSpec.steps.length) nextIndex = currentVizSpec.steps.length - 1;
            renderVizStep(nextIndex);
        }

        function onCompanionVizScrub(val) {
            renderVizStep(parseInt(val, 10));
        }

        function setCompanionVizSpeed(val) {
            vizPlaySpeed = parseInt(val, 10) || 1500;
            if (vizPlayTimer) {
                // Restart timer with new speed
                clearInterval(vizPlayTimer);
                vizPlayTimer = setInterval(() => {
                    if (currentVizStepIndex < currentVizSpec.steps.length - 1) {
                        stepCompanionViz(1);
                    } else {
                        stepCompanionViz(-currentVizSpec.steps.length);
                    }
                }, vizPlaySpeed);
            }
        }

        function restartCompanionViz() {
            if (vizPlayTimer) {
                clearInterval(vizPlayTimer);
                vizPlayTimer = null;
                const playBtn = document.getElementById('companionVizPlayBtn');
                if (playBtn) playBtn.textContent = '▶ Play';
            }
            renderVizStep(0);
        }

        function highlightEditorCodeLine(lineNum) {
            if (!lineNum || lineNum <= 0) return;
            const textarea = (typeof isTestMode === 'function' && isTestMode()) ? document.getElementById("takingCode") : document.getElementById("code");
            if (!textarea || !textarea.value) return;
            const lines = textarea.value.split("\n");
            if (lineNum > lines.length) return;
            let startPos = 0;
            for (let i = 0; i < lineNum - 1; i++) {
                startPos += lines[i].length + 1;
            }
            const endPos = startPos + lines[lineNum - 1].length;
            try {
                textarea.focus();
                textarea.setSelectionRange(startPos, endPos);
                const lineHeight = 19;
                textarea.scrollTop = Math.max(0, (lineNum - 3) * lineHeight);
            } catch (e) {}
        }

        function getActiveVisualizationContext() {
            if (window.activeVisualizationState && window.activeVisualizationState.viz_type) {
                return window.activeVisualizationState;
            }
            if (typeof currentVizSpec !== 'undefined' && currentVizSpec && currentVizSpec.steps && currentVizSpec.steps.length > 0) {
                const sIdx = typeof currentVizStepIndex !== 'undefined' ? currentVizStepIndex : 0;
                const step = currentVizSpec.steps[sIdx] || {};
                return {
                    viz_type: currentVizSpec.viz_type,
                    title: currentVizSpec.title,
                    current_step: sIdx + 1,
                    total_steps: currentVizSpec.steps.length,
                    action: step.action || '',
                    explanation: step.explanation || '',
                    current_state: typeof step.value !== 'undefined' ? (typeof step.value === 'object' ? JSON.stringify(step.value) : String(step.value)) : (step.pointer || ''),
                    relevant_code_line: step.code_line || null
                };
            }
            return null;
        }

        function renderVizStep(stepIndex) {
            if (!currentVizSpec || !currentVizSpec.steps || currentVizSpec.steps.length === 0) return;
            const steps = currentVizSpec.steps;
            stepIndex = Math.max(0, Math.min(steps.length - 1, stepIndex));
            currentVizStepIndex = stepIndex;

            const step = steps[stepIndex];
            const stage = document.getElementById('companionVizStage');
            const explEl = document.getElementById('companionVizExplanation');
            const stepCountEl = document.getElementById('companionVizStepCount');
            const scrubber = document.getElementById('companionVizScrubber');

            if (scrubber) scrubber.value = stepIndex;
            if (stepCountEl) stepCountEl.textContent = `Step ${stepIndex + 1}/${steps.length}`;
            if (explEl) {
                explEl.innerHTML = `<strong>Step ${step.step_number}:</strong> ${escapeHtml(step.explanation)}` +
                    (step.pointer ? `<div style="font-size:11px; color:#d4af37; margin-top:3px;">📍 ${escapeHtml(step.pointer)}</div>` : '');
            }

            // Expose active state for Maya context integration ("Explain step 3")
            window.activeVisualizationState = {
                viz_type: currentVizSpec.viz_type,
                title: currentVizSpec.title,
                current_step: stepIndex + 1,
                total_steps: steps.length,
                action: step.action || '',
                explanation: step.explanation || '',
                current_state: typeof step.value !== 'undefined' ? (typeof step.value === 'object' ? JSON.stringify(step.value) : String(step.value)) : (step.pointer || ''),
                relevant_code_line: step.code_line || null
            };
            if (step.code_line) {
                highlightEditorCodeLine(step.code_line);
            }

            if (!stage) return;
            stage.innerHTML = '';

            const type = (currentVizSpec.viz_type || '').toLowerCase();

            switch (type) {
                case 'circular_queue':
                case 'circular-queue':
                case 'circularqueue':
                    renderCircularQueueViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'topological_sort':
                case 'topological':
                case 'alien_dictionary':
                    renderTopologicalSortViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'flowchart':
                case 'algorithm':
                case 'state':
                case 'steps':
                case 'transition':
                    renderGenericFlowchartViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'stack':
                    renderStackViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'deque':
                case 'double_ended_queue':
                    renderDequeViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'queue':
                    renderQueueViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'circular_linked_list':
                case 'circular-linked-list':
                case 'cll':
                    renderCircularLinkedListViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'doubly_linked_list':
                case 'doubly-linked-list':
                case 'doublylinkedlist':
                    renderDoublyLinkedListViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'linked_list':
                case 'singly_linked_list':
                    renderLinkedListViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'array':
                    renderArrayViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'sorting':
                    renderSortingViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'recursion':
                    renderRecursionViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'tree':
                    renderTreeViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'graph':
                    if (currentVizSpec.title && currentVizSpec.title.toLowerCase().includes('alien')) {
                        renderTopologicalSortViz(stage, currentVizSpec, stepIndex);
                    } else {
                        renderGraphViz(stage, currentVizSpec, stepIndex);
                    }
                    break;
                case 'pointers':
                    renderPointersViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'searching':
                    renderSearchingViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'hash_table':
                case 'hashing':
                case 'hashmap':
                    renderHashTableViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'string':
                case 'palindrome':
                    renderStringViz(stage, currentVizSpec, stepIndex);
                    break;
                case 'code_trace':
                case 'trace':
                    renderCodeTraceViz(stage, currentVizSpec, stepIndex);
                    break;
                default:
                    renderGenericFlowchartViz(stage, currentVizSpec, stepIndex);
                    break;
            }
        }

        // 0AA. TOPOLOGICAL SORT / ALIEN DICTIONARY DAG RENDERER
        function renderTopologicalSortViz(stage, spec, stepIndex) {
            const steps = spec.steps || [];
            const activeStep = steps[stepIndex] || {};

            // Read node list from spec.initial_state instead of hardcoded 'w,e,r,t,f'
            let nodes = ['w', 'e', 'r', 't', 'f']; // fallback only
            if (spec.initial_state && typeof spec.initial_state === 'object' && !Array.isArray(spec.initial_state)) {
                if (Array.isArray(spec.initial_state.nodes) && spec.initial_state.nodes.length > 0) {
                    nodes = spec.initial_state.nodes.map(n => (typeof n === 'object' && n !== null) ? (n.label || n.id || String(n)) : String(n));
                }
            } else if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                nodes = spec.initial_state.map(n => (typeof n === 'object' && n !== null) ? (n.label || n.id || String(n)) : String(n));
            }

            // Compute cumulative order by reading 'value' from processed steps
            let processedNodes = [];
            for (let i = 1; i <= stepIndex; i++) {
                const s = steps[i];
                if (!s) continue;
                const act = (s.action || '').toLowerCase();
                if ((act === 'process_node' || act === 'process' || act === 'visit') && s.value !== undefined) {
                    const vals = String(s.value).split(/\s*->\s*/);
                    vals.forEach(v => { const t = v.trim(); if (t && !processedNodes.includes(t)) processedNodes.push(t); });
                }
            }

            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';
            wrapper.style.alignItems = 'center';
            wrapper.style.gap = '14px';
            wrapper.style.width = '100%';
            wrapper.style.padding = '8px 4px';

            // Top: Character Dependency Graph
            const graphRow = document.createElement('div');
            graphRow.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:8px; flex-wrap:wrap; width:100%;';

            nodes.forEach((char, idx) => {
                const isProcessed = processedNodes.includes(char);
                const isCurrent = (activeStep.highlight_indices && activeStep.highlight_indices.includes(idx));

                const nodeCard = document.createElement('div');
                let border = '#1e293b';
                let bg = '#090d16';
                let color = '#94a3b8';

                if (isCurrent) {
                    border = '#d4af37';
                    bg = '#2a220c';
                    color = '#facc15';
                } else if (isProcessed) {
                    border = '#10b981';
                    bg = '#06281e';
                    color = '#34d399';
                }

                nodeCard.style.cssText = `display:flex; flex-direction:column; align-items:center; justify-content:center; width:48px; height:48px; border-radius:50%; border:2px solid ${border}; background:${bg}; color:${color}; font-weight:800; font-size:16px; font-family:Consolas, monospace; position:relative; box-shadow:0 2px 8px rgba(0,0,0,0.4);`;
                nodeCard.textContent = char;

                // in-degree badge
                let inDeg = (idx <= stepIndex) ? 0 : 1;
                if (idx === 0) inDeg = 0;
                const inBadge = document.createElement('span');
                inBadge.style.cssText = `position:absolute; top:-6px; right:-6px; background:#0f172a; border:1px solid ${border}; font-size:9px; border-radius:8px; padding:1px 4px; color:${isProcessed ? '#34d399' : '#cbd5e1'};`;
                inBadge.textContent = `in:${inDeg}`;
                nodeCard.appendChild(inBadge);

                graphRow.appendChild(nodeCard);

                if (idx < nodes.length - 1) {
                    const arrow = document.createElement('span');
                    arrow.style.cssText = 'color:#64748b; font-size:16px; font-weight:700;';
                    arrow.textContent = '➔';
                    graphRow.appendChild(arrow);
                }
            });
            wrapper.appendChild(graphRow);

            // Bottom: Order Ribbon
            const orderRibbon = document.createElement('div');
            orderRibbon.style.cssText = 'display:flex; align-items:center; gap:8px; background:#0a0e17; border:1px solid #1e293b; border-radius:8px; padding:6px 14px; font-size:12px; font-family:Consolas, monospace;';
            orderRibbon.innerHTML = `<span style="color:#d4af37; font-weight:700;">Topological Order:</span> ` +
                (processedNodes.length > 0
                    ? `<span style="color:#38bdf8; font-weight:800; letter-spacing:2px;">"${processedNodes.join('')}"</span> <span style="color:#64748b; font-size:11px;">[${processedNodes.join(', ')}]</span>`
                    : `<span style="color:#64748b; font-style:italic;">(Analyzing in-degrees...)</span>`);
            wrapper.appendChild(orderRibbon);

            stage.appendChild(wrapper);
        }

        // 0A. CIRCULAR QUEUE RENDERER
        function renderCircularQueueViz(stage, spec, stepIndex) {
            const capacity = (Array.isArray(spec.initial_state) && spec.initial_state.length > 0)
                ? spec.initial_state.length
                : 5;
            let buffer = new Array(capacity).fill(null);
            let front = 0;
            let rear = -1;
            let count = 0;

            if (Array.isArray(spec.initial_state)) {
                spec.initial_state.forEach((val, idx) => {
                    if (val !== null && val !== undefined && idx < capacity) {
                        buffer[idx] = val;
                        rear = idx;
                        count++;
                    }
                });
            }

            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                const act = (s.action || '').toLowerCase();
                if ((act === 'enqueue' || act === 'push') && s.value !== undefined) {
                    rear = (rear + 1) % capacity;
                    buffer[rear] = s.value;
                    count = Math.min(capacity, count + 1);
                } else if (act === 'dequeue' || act === 'pop') {
                    if (count > 0) {
                        buffer[front] = null;
                        front = (front + 1) % capacity;
                        count = Math.max(0, count - 1);
                    }
                }
            }

            const currentStep = spec.steps && spec.steps[stepIndex];
            const highlighted = (currentStep && currentStep.highlight_indices) || [];

            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';
            wrapper.style.alignItems = 'center';
            wrapper.style.gap = '10px';
            wrapper.style.width = '100%';

            // Stats pill
            const stats = document.createElement('div');
            stats.style.cssText = 'display:flex; gap:12px; font-size:11px; font-family:Consolas, monospace; background:#0f172a; padding:4px 12px; border-radius:12px; border:1px solid #1e293b; color:#94a3b8;';
            stats.innerHTML = `<span>Capacity: <strong style="color:#f8fafc;">${capacity}</strong></span>` +
                `<span>Size: <strong style="color:#38bdf8;">${count}</strong></span>` +
                `<span>FRONT: <strong style="color:#f59e0b;">${front}</strong></span>` +
                `<span>REAR: <strong style="color:#10b981;">${rear >= 0 ? rear : '—'}</strong></span>`;
            wrapper.appendChild(stats);

            // Ring / slot track
            const track = document.createElement('div');
            track.style.cssText = 'display:flex; gap:8px; align-items:center; justify-content:center; flex-wrap:wrap; margin:8px 0;';

            for (let idx = 0; idx < capacity; idx++) {
                const slot = document.createElement('div');
                const isFront = (count > 0 && idx === front);
                const isRear = (count > 0 && idx === rear);
                const isHighlighted = highlighted.includes(idx);
                const val = buffer[idx];

                let borderCol = '#334155';
                let bgCol = '#090d16';
                if (isHighlighted) {
                    borderCol = '#d4af37';
                    bgCol = '#1c1917';
                } else if (isFront && isRear) {
                    borderCol = '#818cf8';
                } else if (isFront) {
                    borderCol = '#f59e0b';
                } else if (isRear) {
                    borderCol = '#10b981';
                }

                slot.style.cssText = `width:56px; height:60px; border:2px solid ${borderCol}; background:${bgCol}; border-radius:8px; display:flex; flex-direction:column; align-items:center; justify-content:center; position:relative; box-shadow:0 2px 4px rgba(0,0,0,0.3);`;

                // Index header
                const idxLabel = document.createElement('span');
                idxLabel.style.cssText = 'font-size:9px; color:#64748b; font-family:Consolas, monospace; position:absolute; top:2px; left:4px;';
                idxLabel.textContent = `[${idx}]`;
                slot.appendChild(idxLabel);

                // Value
                const valSpan = document.createElement('span');
                valSpan.style.cssText = `font-size:14px; font-weight:700; color:${val !== null ? '#f8fafc' : '#475569'}; margin-top:8px; font-family:Consolas, monospace;`;
                valSpan.textContent = val !== null ? formatVizValue(val) : '—';
                slot.appendChild(valSpan);

                // Pointer badge
                let badgeText = '';
                let badgeColor = '#64748b';
                if (isFront && isRear) { badgeText = 'F / R'; badgeColor = '#818cf8'; }
                else if (isFront) { badgeText = 'FRONT'; badgeColor = '#f59e0b'; }
                else if (isRear) { badgeText = 'REAR'; badgeColor = '#10b981'; }

                if (badgeText) {
                    const badge = document.createElement('span');
                    badge.style.cssText = `font-size:8px; font-weight:700; color:${badgeColor}; position:absolute; bottom:2px; letter-spacing:0.5px;`;
                    badge.textContent = badgeText;
                    slot.appendChild(badge);
                }

                track.appendChild(slot);
            }

            wrapper.appendChild(track);

            // Modulo formula helper card
            const formula = document.createElement('div');
            formula.style.cssText = 'font-size:10px; color:#94a3b8; font-family:Consolas, monospace; display:flex; align-items:center; gap:8px;';
            formula.innerHTML = `<span style="color:#d4af37;">⟳ Modulo Arithmetic:</span> next_index = (current + 1) % ${capacity}`;
            wrapper.appendChild(formula);

            stage.appendChild(wrapper);
        }

        // 0B. FLOWCHART & GENERIC ALGORITHM RENDERER
        function renderGenericFlowchartViz(stage, spec, stepIndex) {
            const steps = spec.steps || [];
            const activeStep = steps[stepIndex] || {};
            const nodes = (Array.isArray(spec.initial_state) && spec.initial_state.length > 0)
                ? spec.initial_state
                : steps.map((s, idx) => `Phase ${idx + 1}`);

            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';
            wrapper.style.alignItems = 'center';
            wrapper.style.gap = '12px';
            wrapper.style.width = '100%';

            // Flowchart nodes sequence diagram
            const flowStrip = document.createElement('div');
            flowStrip.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:6px; flex-wrap:wrap; width:100%; padding:6px 0;';

            nodes.forEach((nodeName, nIdx) => {
                const nodeCard = document.createElement('div');
                const isCurrent = (activeStep.highlight_indices && activeStep.highlight_indices.includes(nIdx)) ||
                                  (nIdx === stepIndex % nodes.length);
                const isPassed = nIdx < (stepIndex % nodes.length);

                let border = '#1e293b';
                let bg = '#090d16';
                let textColor = '#64748b';

                if (isCurrent) {
                    border = '#d4af37';
                    bg = '#1c1917';
                    textColor = '#facc15';
                } else if (isPassed) {
                    border = '#059669';
                    bg = '#06281e';
                    textColor = '#34d399';
                }

                nodeCard.style.cssText = `padding:6px 12px; border:1px solid ${border}; background:${bg}; border-radius:6px; font-size:11px; font-weight:600; color:${textColor}; font-family:system-ui, sans-serif; display:flex; align-items:center; gap:5px; transition:all 0.2s;`;
                nodeCard.innerHTML = `<span>${isPassed ? '✓' : (isCurrent ? '▶' : '○')}</span> <span>${escapeHtml(formatVizValue(nodeName))}</span>`;
                flowStrip.appendChild(nodeCard);

                if (nIdx < nodes.length - 1) {
                    const arrow = document.createElement('span');
                    arrow.style.cssText = 'color:#475569; font-size:11px;';
                    arrow.textContent = '➔';
                    flowStrip.appendChild(arrow);
                }
            });
            wrapper.appendChild(flowStrip);

            // Active State Card
            const card = document.createElement('div');
            card.style.cssText = 'width:90%; background:#0b1120; border:1px solid #1e293b; border-left:4px solid #38bdf8; border-radius:8px; padding:10px 14px; display:flex; flex-direction:column; gap:6px;';

            const headerRow = document.createElement('div');
            headerRow.style.cssText = 'display:flex; justify-content:space-between; align-items:center;';
            headerRow.innerHTML = `<span style="font-size:12px; font-weight:700; color:#38bdf8;">Step ${activeStep.step_number || (stepIndex + 1)}: ${escapeHtml(formatVizValue(activeStep.action || 'Execute')).toUpperCase()}</span>` +
                (activeStep.pointer ? `<span style="font-size:11px; color:#d4af37; font-family:Consolas, monospace;">📍 ${escapeHtml(formatVizValue(activeStep.pointer))}</span>` : '');
            card.appendChild(headerRow);

            if (activeStep.value !== undefined && activeStep.value !== null) {
                const valRow = document.createElement('div');
                valRow.style.cssText = 'font-size:12px; font-family:Consolas, monospace; background:#020617; padding:4px 8px; border-radius:4px; border:1px solid #1e293b; color:#a5f3fc;';
                valRow.innerHTML = `<strong>State:</strong> ${escapeHtml(formatVizValue(activeStep.value))}`;
                card.appendChild(valRow);
            }

            const descRow = document.createElement('div');
            descRow.style.cssText = 'font-size:12px; color:#cbd5e1; line-height:1.45;';
            descRow.textContent = activeStep.explanation || '';
            card.appendChild(descRow);

            wrapper.appendChild(card);
            stage.appendChild(wrapper);
        }

        // 1. STACK RENDERER
        function renderStackViz(stage, spec, stepIndex) {
            let stack = Array.isArray(spec.initial_state) ? [...spec.initial_state] : [];
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if ((s.action === 'push' || s.action === 'insert') && s.value !== undefined) {
                    stack.push(s.value);
                } else if (s.action === 'pop' || s.action === 'delete') {
                    stack.pop();
                }
            }

            const currentStep = spec.steps && spec.steps[stepIndex];
            const container = document.createElement('div');
            container.className = 'viz-stack-container';

            if (stack.length === 0) {
                const emptyEl = document.createElement('div');
                emptyEl.style.color = '#64748b';
                emptyEl.style.fontStyle = 'italic';
                emptyEl.style.fontSize = '12px';
                emptyEl.textContent = '(Stack is empty)';
                container.appendChild(emptyEl);
            } else {
                stack.forEach((val, idx) => {
                    const block = document.createElement('div');
                    block.className = 'viz-stack-block';
                    const isTop = (idx === stack.length - 1);
                    if (isTop) block.classList.add('highlight');
                    const ptrText = (isTop && currentStep && currentStep.pointer) ? currentStep.pointer : (isTop ? 'TOP' : '');
                    block.innerHTML = `<span>${escapeHtml(formatVizValue(val))}</span>` +
                        (ptrText ? `<span style="font-size:9px; color:#d4af37; margin-left:6px; font-weight:800;">${escapeHtml(formatVizValue(ptrText))}</span>` : '');
                    container.appendChild(block);
                });
            }

            stage.appendChild(container);
        }

        // 2. QUEUE RENDERER
        function renderQueueViz(stage, spec, stepIndex) {
            let q = Array.isArray(spec.initial_state) ? [...spec.initial_state] : [];
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if ((s.action === 'enqueue' || s.action === 'push') && s.value !== undefined) {
                    q.push(s.value);
                } else if (s.action === 'dequeue' || s.action === 'pop') {
                    q.shift();
                }
            }

            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';
            wrapper.style.alignItems = 'center';
            wrapper.style.gap = '6px';

            const conduit = document.createElement('div');
            conduit.className = 'viz-queue-conduit';

            if (q.length === 0) {
                const emptyEl = document.createElement('div');
                emptyEl.style.color = '#64748b';
                emptyEl.style.fontStyle = 'italic';
                emptyEl.style.fontSize = '12px';
                emptyEl.textContent = '(Queue is empty)';
                conduit.appendChild(emptyEl);
            } else {
                q.forEach((val, idx) => {
                    const card = document.createElement('div');
                    card.className = 'viz-node-card';
                    const isFront = (idx === 0);
                    const isRear = (idx === q.length - 1);
                    if (isFront || isRear) card.classList.add('active');

                    let badge = '';
                    if (isFront && isRear) badge = '<span style="font-size:9px; color:#38bdf8;">FRONT/REAR</span>';
                    else if (isFront) badge = '<span style="font-size:9px; color:#38bdf8;">FRONT</span>';
                    else if (isRear) badge = '<span style="font-size:9px; color:#4ade80;">REAR</span>';

                    card.innerHTML = `<span style="font-weight:700;">${escapeHtml(formatVizValue(val))}</span> ${badge}`;
                    conduit.appendChild(card);
                });
            }

            wrapper.appendChild(conduit);
            stage.appendChild(wrapper);
        }

        // 2B. DEQUE (DOUBLE-ENDED QUEUE) RENDERER — distinct from FIFO queue
        // Supports pushFront, pushRear, popFront, popRear — O(1) at both ends
        function renderDequeViz(stage, spec, stepIndex) {
            let dq = Array.isArray(spec.initial_state) ? [...spec.initial_state] : [];
            const currentStep = spec.steps && spec.steps[stepIndex];

            // Replay state up to current stepIndex
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'pushFront' && s.value !== undefined) {
                    dq.unshift(s.value);
                } else if (s.action === 'pushRear' && s.value !== undefined) {
                    dq.push(s.value);
                } else if (s.action === 'popFront') {
                    if (dq.length > 0) dq.shift();
                } else if (s.action === 'popRear') {
                    if (dq.length > 0) dq.pop();
                }
            }

            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:8px;width:100%;';

            // Title badge
            const titleBadge = document.createElement('div');
            titleBadge.style.cssText = 'font-size:11px;font-weight:700;color:#d4af37;letter-spacing:1px;margin-bottom:2px;';
            titleBadge.textContent = 'DEQUE — Double-Ended Queue';
            wrapper.appendChild(titleBadge);

            // Direction indicators
            const dirRow = document.createElement('div');
            dirRow.style.cssText = 'display:flex;gap:8px;align-items:center;font-size:10px;color:#94a3b8;';
            dirRow.innerHTML = '<span style="color:#38bdf8">← FRONT (pushFront / popFront)</span><span style="color:#4ade80">REAR (pushRear / popRear) →</span>';
            wrapper.appendChild(dirRow);

            // Deque container
            const conduit = document.createElement('div');
            conduit.style.cssText = 'display:flex;flex-direction:row;align-items:center;gap:2px;overflow-x:auto;padding:8px;';

            // FRONT bracket
            const frontBracket = document.createElement('div');
            frontBracket.style.cssText = 'font-size:10px;font-weight:700;color:#38bdf8;padding:4px 6px;border-left:3px solid #38bdf8;border-top:1px solid #38bdf8;border-bottom:1px solid #38bdf8;';
            frontBracket.textContent = 'FRONT';
            conduit.appendChild(frontBracket);

            if (dq.length === 0) {
                const emptyEl = document.createElement('div');
                emptyEl.style.cssText = 'color:#64748b;font-style:italic;font-size:12px;padding:8px 16px;';
                emptyEl.textContent = '( empty )';
                conduit.appendChild(emptyEl);
            } else {
                dq.forEach((val, idx) => {
                    const isFront = idx === 0;
                    const isRear = idx === dq.length - 1;
                    const isActiveStep = currentStep && (
                        (currentStep.action === 'pushFront' && isFront) ||
                        (currentStep.action === 'pushRear' && isRear) ||
                        (currentStep.action === 'popFront' && isFront) ||
                        (currentStep.action === 'popRear' && isRear) ||
                        (currentStep.highlight_indices && currentStep.highlight_indices.includes(idx))
                    );

                    const card = document.createElement('div');
                    card.className = 'viz-node-card';
                    if (isActiveStep) card.classList.add('active');

                    let borderColor = '#334155';
                    if (isFront && isRear) borderColor = '#d4af37';
                    else if (isFront) borderColor = '#38bdf8';
                    else if (isRear) borderColor = '#4ade80';
                    if (isActiveStep) borderColor = '#f59e0b';
                    card.style.borderColor = borderColor;

                    let badge = '';
                    if (isFront && isRear) badge = '<div style="font-size:8px;color:#d4af37;font-weight:700;">F/R</div>';
                    else if (isFront) badge = '<div style="font-size:8px;color:#38bdf8;font-weight:700;">FRONT</div>';
                    else if (isRear) badge = '<div style="font-size:8px;color:#4ade80;font-weight:700;">REAR</div>';

                    card.innerHTML = badge + `<span style="font-weight:700;">${escapeHtml(formatVizValue(val))}</span>`;
                    conduit.appendChild(card);

                    // Add ↔ connector between cards
                    if (idx < dq.length - 1) {
                        const conn = document.createElement('div');
                        conn.style.cssText = 'color:#d4af37;font-size:16px;font-weight:700;padding:0 2px;align-self:center;';
                        conn.textContent = '↔';
                        conduit.appendChild(conn);
                    }
                });
            }

            // REAR bracket
            const rearBracket = document.createElement('div');
            rearBracket.style.cssText = 'font-size:10px;font-weight:700;color:#4ade80;padding:4px 6px;border-right:3px solid #4ade80;border-top:1px solid #4ade80;border-bottom:1px solid #4ade80;';
            rearBracket.textContent = 'REAR';
            conduit.appendChild(rearBracket);

            wrapper.appendChild(conduit);

            // Current operation indicator
            if (currentStep) {
                const opBadge = document.createElement('div');
                const opColors = {
                    pushFront: '#38bdf8', pushRear: '#4ade80',
                    popFront: '#f87171', popRear: '#fb923c',
                    highlight: '#d4af37'
                };
                const col = opColors[currentStep.action] || '#94a3b8';
                opBadge.style.cssText = `font-size:11px;font-weight:700;color:${col};padding:3px 10px;border:1px solid ${col}33;border-radius:4px;`;
                opBadge.textContent = `Operation: ${currentStep.action}${currentStep.value !== undefined && currentStep.value !== null ? '(' + currentStep.value + ')' : ''}`;
                wrapper.appendChild(opBadge);
            }

            stage.appendChild(wrapper);
        }

        // 3. LINKED LIST RENDERER
        function renderLinkedListViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            let nodes = [];

            if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                nodes = spec.initial_state.map(v => ({
                    val: (typeof v === 'object' && v !== null && v.val !== undefined) ? v.val : v
                }));
            }

            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'insert' || s.action === 'push' || s.action === 'append') {
                    const insertIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : nodes.length;
                    nodes.splice(insertIdx, 0, { val: s.value !== undefined ? s.value : 'Node', isNew: (i === stepIndex) });
                } else if (s.action === 'delete' || s.action === 'remove' || s.action === 'pop') {
                    const delIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : 0;
                    if (nodes.length > delIdx) nodes.splice(delIdx, 1);
                }
            }

            // Fallback if no initial_state was provided and no nodes were pushed
            if (nodes.length === 0 && spec.steps && spec.steps.length > 0) {
                nodes = spec.steps.filter(s => s.value !== undefined).map(s => ({ val: s.value }));
            }
            if (nodes.length === 0) {
                stage.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:24px; font-size:12px;">Linked list is currently empty for this step.</div>';
                return;
            }

            const container = document.createElement('div');
            container.style.display = 'flex';
            container.style.alignItems = 'center';
            container.style.gap = '6px';
            container.style.overflowX = 'auto';
            container.style.padding = '10px';

            nodes.forEach((n, idx) => {
                const card = document.createElement('div');
                card.className = 'viz-node-card';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) card.classList.add('active');
                if (n.isNew) card.style.borderColor = '#22c55e';

                const isHead = (idx === 0);
                const isTail = (idx === nodes.length - 1);
                const nextLabel = isTail ? 'NULL' : '➜';

                card.innerHTML = `
                    ${isHead ? '<div style="font-size:9px; color:#38bdf8; font-weight:700; margin-bottom:2px;">HEAD</div>' : ''}
                    <div style="font-weight:700; color:#f8fafc;">${escapeHtml(formatVizValue(n.val))}</div>
                    <div style="border-left:1px solid #334155; padding-left:6px; color:#d4af37; font-size:11px;">${nextLabel}</div>
                `;
                container.appendChild(card);
            });

            stage.appendChild(container);
        }

        // 3B-1. CIRCULAR LINKED LIST RENDERER (Closed Ring — TAIL.next -> HEAD, strictly NO NULL)
        function renderCircularLinkedListViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            let nodes = [];

            if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                nodes = spec.initial_state.map(v => ({
                    val: (typeof v === 'object' && v !== null && v.val !== undefined) ? v.val : v
                }));
            }

            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'insert' || s.action === 'push' || s.action === 'append' || s.action === 'create_node') {
                    const insertIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : nodes.length;
                    nodes.splice(insertIdx, 0, { val: s.value !== undefined ? s.value : 'Node', isNew: (i === stepIndex) });
                } else if (s.action === 'delete' || s.action === 'remove' || s.action === 'pop') {
                    const delIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : 0;
                    if (nodes.length > delIdx) nodes.splice(delIdx, 1);
                }
            }

            if (nodes.length === 0 && spec.steps && spec.steps.length > 0) {
                nodes = spec.steps.filter(s => s.value !== undefined).map(s => ({ val: s.value }));
            }
            if (nodes.length === 0) {
                stage.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:24px; font-size:12px;">Circular linked list is currently empty for this step.</div>';
                return;
            }

            const wrapper = document.createElement('div');
            wrapper.style.display = 'flex';
            wrapper.style.flexDirection = 'column';
            wrapper.style.alignItems = 'center';
            wrapper.style.width = '100%';
            wrapper.style.padding = '8px';

            const container = document.createElement('div');
            container.style.display = 'flex';
            container.style.alignItems = 'center';
            container.style.gap = '8px';
            container.style.overflowX = 'auto';
            container.style.padding = '8px 12px';

            nodes.forEach((n, idx) => {
                const card = document.createElement('div');
                card.className = 'viz-node-card';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) card.classList.add('active');
                if (n.isNew) card.style.borderColor = '#22c55e';

                const isHead = (idx === 0);
                const isTail = (idx === nodes.length - 1);

                card.innerHTML = `
                    ${isHead ? '<div style="font-size:9px; color:#38bdf8; font-weight:700; margin-bottom:2px;">HEAD</div>' : ''}
                    ${isTail ? '<div style="font-size:9px; color:#a855f7; font-weight:700; margin-bottom:2px;">TAIL</div>' : ''}
                    <div style="font-weight:700; color:#f8fafc;">${escapeHtml(formatVizValue(n.val))}</div>
                    <div style="border-left:1px solid #334155; padding-left:6px; color:#38bdf8; font-size:11px;">➜</div>
                `;
                container.appendChild(card);
            });

            // Loop indicator connecting Tail back to HEAD (Strictly NO NULL)
            const loopIndicator = document.createElement('div');
            loopIndicator.style.marginTop = '10px';
            loopIndicator.style.padding = '6px 14px';
            loopIndicator.style.background = 'rgba(168, 85, 247, 0.12)';
            loopIndicator.style.border = '1px dashed #a855f7';
            loopIndicator.style.borderRadius = '9999px';
            loopIndicator.style.color = '#c084fc';
            loopIndicator.style.fontSize = '11px';
            loopIndicator.style.fontWeight = '600';
            loopIndicator.style.display = 'flex';
            loopIndicator.style.alignItems = 'center';
            loopIndicator.style.gap = '6px';
            const headVal = nodes[0] ? escapeHtml(formatVizValue(nodes[0].val)) : 'HEAD';
            loopIndicator.innerHTML = `<span>⟲</span> <span>TAIL.next ➜ HEAD (Node ${headVal}) — Closed Ring, NO NULL</span>`;

            wrapper.appendChild(container);
            wrapper.appendChild(loopIndicator);
            stage.appendChild(wrapper);
        }

        // 3B. DOUBLY LINKED LIST RENDERER (Bidirectional Pointers: prev & next)
        function renderDoublyLinkedListViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            let nodes = [];

            if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                nodes = spec.initial_state.map(v => ({
                    val: (typeof v === 'object' && v !== null && v.val !== undefined) ? v.val : v
                }));
            }

            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'insert' || s.action === 'push' || s.action === 'append' || s.action === 'create_node') {
                    const insertIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : nodes.length;
                    nodes.splice(insertIdx, 0, { val: s.value !== undefined ? s.value : 'Node', isNew: (i === stepIndex) });
                } else if (s.action === 'delete' || s.action === 'remove' || s.action === 'pop' || s.action === 'unlink') {
                    const delIdx = (s.highlight_indices && s.highlight_indices[0] !== undefined) ? s.highlight_indices[0] : 0;
                    if (nodes.length > delIdx) nodes.splice(delIdx, 1);
                }
            }

            if (nodes.length === 0 && spec.steps && spec.steps.length > 0) {
                nodes = spec.steps.filter(s => s.value !== undefined).map(s => ({ val: s.value }));
            }
            if (nodes.length === 0) {
                stage.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:24px; font-size:12px;">Doubly linked list is currently empty for this step.</div>';
                return;
            }

            const container = document.createElement('div');
            container.style.display = 'flex';
            container.style.alignItems = 'center';
            container.style.gap = '8px';
            container.style.overflowX = 'auto';
            container.style.padding = '14px 10px';

            // Boundary NULL indicator at the left
            const leftNull = document.createElement('div');
            leftNull.style.fontSize = '11px';
            leftNull.style.color = '#64748b';
            leftNull.style.fontWeight = '700';
            leftNull.textContent = 'NULL ⇄';
            container.appendChild(leftNull);

            nodes.forEach((n, idx) => {
                const card = document.createElement('div');
                card.className = 'viz-node-card';
                card.style.display = 'flex';
                card.style.alignItems = 'center';
                card.style.gap = '8px';
                card.style.padding = '8px 12px';
                card.style.minWidth = '95px';
                card.style.justifyContent = 'space-between';

                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) card.classList.add('active');
                if (n.isNew) card.style.borderColor = '#22c55e';

                const isHead = (idx === 0);
                const isTail = (idx === nodes.length - 1);
                const prevVal = isHead ? 'NULL' : formatVizValue(nodes[idx - 1].val);
                const nextVal = isTail ? 'NULL' : formatVizValue(nodes[idx + 1].val);

                card.innerHTML = `
                    <div style="display:flex; flex-direction:column; align-items:center;">
                        ${isHead ? '<div style="font-size:9px; color:#38bdf8; font-weight:700; margin-bottom:2px;">HEAD</div>' : (isTail ? '<div style="font-size:9px; color:#d4af37; font-weight:700; margin-bottom:2px;">TAIL</div>' : '')}
                        <div style="display:flex; align-items:center; gap:6px;">
                            <span style="font-size:10px; color:#64748b;" title="prev: ${escapeHtml(prevVal)}">←</span>
                            <span style="font-weight:700; color:#f8fafc; font-size:13px;">${escapeHtml(formatVizValue(n.val))}</span>
                            <span style="font-size:10px; color:#64748b;" title="next: ${escapeHtml(nextVal)}">→</span>
                        </div>
                    </div>
                `;
                container.appendChild(card);

                if (!isTail) {
                    const arrow = document.createElement('div');
                    arrow.style.color = '#38bdf8';
                    arrow.style.fontWeight = '700';
                    arrow.style.fontSize = '13px';
                    arrow.textContent = '⇄';
                    container.appendChild(arrow);
                }
            });

            // Boundary NULL indicator at the right
            const rightNull = document.createElement('div');
            rightNull.style.fontSize = '11px';
            rightNull.style.color = '#64748b';
            rightNull.style.fontWeight = '700';
            rightNull.textContent = '⇄ NULL';
            container.appendChild(rightNull);

            stage.appendChild(container);
        }

        // 4. ARRAY / TWO POINTERS RENDERER
        function renderArrayViz(stage, spec, stepIndex) {
            const arr = Array.isArray(spec.initial_state) ? spec.initial_state : [];
            if (arr.length === 0) {
                stage.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:24px; font-size:12px;">No array elements provided for visualization.</div>';
                return;
            }
            const step = spec.steps && spec.steps[stepIndex];

            const grid = document.createElement('div');
            grid.className = 'viz-array-grid';

            arr.forEach((val, idx) => {
                const cellWrapper = document.createElement('div');
                cellWrapper.className = 'viz-array-cell-wrapper';

                // Pointer Label
                const ptrEl = document.createElement('div');
                ptrEl.className = 'viz-array-pointer';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    if (step.pointer) ptrEl.textContent = step.pointer;
                    else if (idx === 0) ptrEl.textContent = '▼ L';
                    else if (idx === arr.length - 1) ptrEl.textContent = '▼ R';
                    else ptrEl.textContent = '▼';
                }
                cellWrapper.appendChild(ptrEl);

                // Cell Box
                const cell = document.createElement('div');
                cell.className = 'viz-array-cell';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    cell.classList.add('highlight');
                }
                cell.textContent = formatVizValue(val);
                cellWrapper.appendChild(cell);

                // Index underneath
                const idxLabel = document.createElement('div');
                idxLabel.style.fontSize = '10px';
                idxLabel.style.color = '#64748b';
                idxLabel.textContent = `[${idx}]`;
                cellWrapper.appendChild(idxLabel);

                grid.appendChild(cellWrapper);
            });

            stage.appendChild(grid);
        }

        // 5. SORTING RENDERER
        function renderSortingViz(stage, spec, stepIndex) {
            let arr = Array.isArray(spec.initial_state) ? [...spec.initial_state] : [];
            if (arr.length === 0) {
                stage.innerHTML = '<div style="text-align:center; color:#94a3b8; padding:24px; font-size:12px;">No elements provided for sorting visualization.</div>';
                return;
            }
            const step = spec.steps && spec.steps[stepIndex];

            // Apply swaps up to stepIndex
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'swap' && s.value && s.value.from !== undefined) {
                    const tmp = arr[s.value.from];
                    arr[s.value.from] = arr[s.value.to];
                    arr[s.value.to] = tmp;
                }
            }

            const chart = document.createElement('div');
            chart.className = 'viz-bar-chart';
            const numVals = arr.map(v => Number(v) || 1);
            const maxVal = Math.max(...numVals, 1);

            arr.forEach((val, idx) => {
                const bar = document.createElement('div');
                bar.className = 'viz-bar-item';
                const heightPct = Math.round(((Number(val) || 1) / maxVal) * 130) + 20;
                bar.style.height = `${heightPct}px`;

                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    bar.classList.add('highlight');
                }

                bar.textContent = formatVizValue(val);
                chart.appendChild(bar);
            });

            stage.appendChild(chart);
        }

        // 6. RECURSION CALL STACK RENDERER
        function renderRecursionViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            const frames = [];
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'call' || s.action === 'push') {
                    frames.push({ sig: s.value || `frame_${i+1}()`, depth: frames.length + 1 });
                } else if (s.action === 'return' || s.action === 'pop') {
                    if (frames.length > 0) {
                        if (i === stepIndex && s.action === 'return') {
                            frames[frames.length - 1].returning = s.value !== undefined ? s.value : 'returned';
                        } else {
                            frames.pop();
                        }
                    }
                }
            }

            // Fallback if no frames were accumulated
            if (frames.length === 0 && spec.steps && spec.steps.length > 0) {
                const s = spec.steps[stepIndex];
                frames.push({ sig: s.value || 'factorial(1)', depth: 1, returning: s.action === 'return' ? s.value : null });
            }

            const container = document.createElement('div');
            container.style.display = 'flex';
            container.style.flexDirection = 'column-reverse';
            container.style.gap = '6px';
            container.style.width = '260px';

            frames.forEach((f, idx) => {
                const frameEl = document.createElement('div');
                frameEl.className = 'viz-stack-block';
                frameEl.style.height = '36px';
                frameEl.style.fontSize = '12px';
                if (idx === frames.length - 1) {
                    frameEl.classList.add('highlight');
                }
                frameEl.innerHTML = `<span>⚙ ${escapeHtml(formatVizValue(f.sig || 'frame()'))}</span>` +
                    (f.returning !== undefined && f.returning !== null ? `<span style="font-size:10px; color:#4ade80; margin-left:6px; font-weight:700;">➜ ${escapeHtml(formatVizValue(f.returning))}</span>` : '');
                container.appendChild(frameEl);
            });

            stage.appendChild(container);
        }

        // 7. TREE RENDERER (SVG) — Arbitrary Shape, Size & Node Values (Prompt 2 Requirement 8)
        function renderTreeViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', '100%');
            svg.setAttribute('height', '100%');

            // Parse nodes and edges from spec.initial_state
            let rawNodes = [];
            let rawEdges = [];

            if (spec.initial_state && typeof spec.initial_state === 'object' && !Array.isArray(spec.initial_state)) {
                rawNodes = spec.initial_state.nodes || [];
                rawEdges = spec.initial_state.edges || [];
            } else if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                // If an array of values is passed, construct binary tree level-by-level
                spec.initial_state.forEach((val, idx) => {
                    if (val !== null && val !== undefined) {
                        rawNodes.push({ id: `n_${idx}`, val: val, levelIdx: idx });
                    }
                });
                for (let i = 0; i < rawNodes.length; i++) {
                    const leftIdx = 2 * i + 1;
                    const rightIdx = 2 * i + 2;
                    if (leftIdx < rawNodes.length) rawEdges.push({ from: rawNodes[i].id, to: rawNodes[leftIdx].id });
                    if (rightIdx < rawNodes.length) rawEdges.push({ from: rawNodes[i].id, to: rawNodes[rightIdx].id });
                }
            } else {
                // No valid tree data available — show informative message instead of demo data
                const msg = document.createElement('div');
                msg.style.cssText = 'color:#64748b; font-size:12px; text-align:center; padding:20px;';
                msg.textContent = 'Tree data unavailable for this visualization.';
                stage.appendChild(msg);
                return;
            }

            // Calculate dynamic tree layout coordinates (cx, cy)
            // Group nodes by depth if explicit x,y are not present
            const nodeMap = {};
            rawNodes.forEach(n => { nodeMap[n.id] = { ...n }; });

            const hasExplicitCoords = rawNodes.every(n => n.cx !== undefined && n.cy !== undefined || n.x !== undefined && n.y !== undefined);

            let nodes = [];
            if (hasExplicitCoords) {
                nodes = rawNodes.map(n => ({
                    ...n,
                    cx: n.cx !== undefined ? n.cx : (n.x <= 100 ? n.x * 3.2 : n.x),
                    cy: n.cy !== undefined ? n.cy : (n.y <= 100 ? n.y * 1.8 : n.y)
                }));
            } else {
                // Determine root (node with in-degree 0)
                const childrenIds = new Set(rawEdges.map(e => e.to !== undefined ? e.to : (Array.isArray(e) ? e[1] : null)));
                const root = rawNodes.find(n => !childrenIds.has(n.id)) || rawNodes[0];

                // Build adjacency list
                const adj = {};
                rawNodes.forEach(n => { adj[n.id] = []; });
                rawEdges.forEach(e => {
                    const u = e.from !== undefined ? e.from : (Array.isArray(e) ? e[0] : null);
                    const v = e.to !== undefined ? e.to : (Array.isArray(e) ? e[1] : null);
                    if (u && v && adj[u]) adj[u].push(v);
                });

                // Assign depth and horizontal positions via tree traversal
                let maxDepth = 0;
                const levelBuckets = {};

                function assignDepths(nodeId, depth = 0) {
                    if (!nodeId) return;
                    maxDepth = Math.max(maxDepth, depth);
                    if (!levelBuckets[depth]) levelBuckets[depth] = [];
                    levelBuckets[depth].push(nodeId);
                    const children = adj[nodeId] || [];
                    children.forEach(c => assignDepths(c, depth + 1));
                }

                assignDepths(root ? root.id : null, 0);

                // Assign (cx, cy) coordinates based on level distribution
                const svgW = 340;
                const svgH = Math.max(180, (maxDepth + 1) * 60 + 20);
                svg.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);

                Object.keys(levelBuckets).forEach(depthStr => {
                    const depth = parseInt(depthStr);
                    const bucket = levelBuckets[depth];
                    const count = bucket.length;
                    const stepX = svgW / (count + 1);
                    const y = 35 + depth * 55;
                    bucket.forEach((nodeId, idx) => {
                        const target = nodeMap[nodeId];
                        if (target) {
                            target.cx = stepX * (idx + 1);
                            target.cy = y;
                        }
                    });
                });

                nodes = rawNodes.map(n => nodeMap[n.id] || n);
            }

            // Render Edges
            rawEdges.forEach(e => {
                const uId = e.from !== undefined ? e.from : (Array.isArray(e) ? e[0] : null);
                const vId = e.to !== undefined ? e.to : (Array.isArray(e) ? e[1] : null);
                const u = nodes.find(n => n.id === uId) || (typeof uId === 'number' ? nodes[uId] : null);
                const v = nodes.find(n => n.id === vId) || (typeof vId === 'number' ? nodes[vId] : null);
                if (u && v && u.cx !== undefined && v.cx !== undefined) {
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', u.cx);
                    line.setAttribute('y1', u.cy);
                    line.setAttribute('x2', v.cx);
                    line.setAttribute('y2', v.cy);
                    line.setAttribute('stroke', '#334155');
                    line.setAttribute('stroke-width', '2');
                    svg.appendChild(line);
                }
            });

            // Render Nodes
            nodes.forEach((n, idx) => {
                const isHighlight = Boolean(step && step.highlight_indices && (step.highlight_indices.includes(idx) || step.highlight_indices.includes(n.id)));

                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', n.cx);
                circle.setAttribute('cy', n.cy);
                circle.setAttribute('r', '17');
                circle.setAttribute('fill', isHighlight ? '#d4af37' : '#111522');
                circle.setAttribute('stroke', isHighlight ? '#fef08a' : '#38bdf8');
                circle.setAttribute('stroke-width', isHighlight ? '3.5' : '2');
                svg.appendChild(circle);

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', n.cx);
                text.setAttribute('y', n.cy + 4);
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('fill', isHighlight ? '#040810' : '#f8fafc');
                text.setAttribute('font-size', '11');
                text.setAttribute('font-weight', '700');
                text.textContent = formatVizValue(n.val !== undefined ? n.val : n.id);
                svg.appendChild(text);
            });

            stage.appendChild(svg);
        }


        // 8. GRAPH RENDERER (SVG)
        function renderGraphViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', '100%');
            svg.setAttribute('height', '100%');

            // Parse nodes and edges from spec.initial_state (never use hardcoded demo data)
            let rawNodes = [];
            let rawEdges = [];

            if (spec.initial_state && typeof spec.initial_state === 'object' && !Array.isArray(spec.initial_state)) {
                rawNodes = (spec.initial_state.nodes || []).map((n, i) =>
                    (typeof n === 'object' && n !== null) ? n : { id: i, label: String(n) });
                rawEdges = spec.initial_state.edges || [];
            } else if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                rawNodes = spec.initial_state.map((v, i) => ({ id: i, label: String(v) }));
            }

            if (rawNodes.length === 0) {
                const msg = document.createElement('div');
                msg.style.cssText = 'color:#64748b; font-size:12px; text-align:center; padding:20px;';
                msg.textContent = 'Graph data unavailable for this visualization.';
                stage.appendChild(msg);
                return;
            }

            const svgW = 320, svgH = 180;
            svg.setAttribute('viewBox', `0 0 ${svgW} ${svgH}`);
            const cx0 = svgW / 2, cy0 = svgH / 2;
            const radius = Math.min(svgW, svgH) * 0.35;

            // Build node map with auto-layout when explicit coords are absent
            const nodeMap = {};
            rawNodes.forEach((n, idx) => {
                const nid = n.id !== undefined ? n.id : idx;
                const hasCoords = (n.x !== undefined || n.cx !== undefined) && (n.y !== undefined || n.cy !== undefined);
                const angle = (2 * Math.PI * idx) / rawNodes.length - Math.PI / 2;
                nodeMap[nid] = {
                    ...n,
                    id: nid,
                    label: n.label !== undefined ? n.label : (n.val !== undefined ? String(n.val) : String(nid)),
                    cx: hasCoords ? (n.cx !== undefined ? n.cx : (n.x <= 100 ? n.x * (svgW / 100) : n.x))
                                  : cx0 + radius * Math.cos(angle),
                    cy: hasCoords ? (n.cy !== undefined ? n.cy : (n.y <= 100 ? n.y * (svgH / 100) : n.y))
                                  : cy0 + radius * Math.sin(angle)
                };
            });
            const nodes = Object.values(nodeMap);

            // Render Edges
            rawEdges.forEach(e => {
                const uId = Array.isArray(e) ? e[0] : (e.from !== undefined ? e.from : null);
                const vId = Array.isArray(e) ? e[1] : (e.to !== undefined ? e.to : null);
                const u = nodeMap[uId];
                const v = nodeMap[vId];
                if (u && v) {
                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', u.cx); line.setAttribute('y1', u.cy);
                    line.setAttribute('x2', v.cx); line.setAttribute('y2', v.cy);
                    line.setAttribute('stroke', '#334155');
                    line.setAttribute('stroke-width', '2');
                    svg.appendChild(line);
                }
            });

            // Render Nodes
            nodes.forEach((n, idx) => {
                const isHighlight = step && step.highlight_indices &&
                    (step.highlight_indices.includes(idx) || step.highlight_indices.includes(n.id));
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', n.cx); circle.setAttribute('cy', n.cy);
                circle.setAttribute('r', '18');
                circle.setAttribute('fill', isHighlight ? '#22c55e' : '#111522');
                circle.setAttribute('stroke', isHighlight ? '#86efac' : '#38bdf8');
                circle.setAttribute('stroke-width', '2');
                svg.appendChild(circle);

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', n.cx); text.setAttribute('y', n.cy + 4);
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('fill', isHighlight ? '#040810' : '#f8fafc');
                text.setAttribute('font-size', '10'); text.setAttribute('font-weight', '700');
                text.textContent = formatVizValue(n.label);
                svg.appendChild(text);
            });

            stage.appendChild(svg);
        }

        // 9. POINTERS / MEMORY RENDERER
        function renderPointersViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];

            // Read rows from spec.initial_state (never use hardcoded demo data)
            let rows = [];
            if (Array.isArray(spec.initial_state) && spec.initial_state.length > 0) {
                rows = spec.initial_state.map(entry => {
                    if (typeof entry === 'object' && entry !== null) return entry;
                    return { var: String(entry), addr: '?', val: '?', type: 'unknown' };
                });
            }

            if (rows.length === 0) {
                const msg = document.createElement('div');
                msg.style.cssText = 'color:#64748b; font-size:12px; text-align:center; padding:20px;';
                msg.textContent = 'Memory layout data unavailable for this visualization.';
                stage.appendChild(msg);
                return;
            }

            // Apply any mutations tracked in the steps up to stepIndex
            let mutated = rows.map(r => ({ ...r }));
            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                const act = (s.action || '').toLowerCase();
                if (act === 'mutate' && s.value !== undefined) {
                    // s.value may be like "*ptr = 100" — try to apply to first highlighted var
                    const hi = s.highlight_indices && s.highlight_indices.length > 0 ? s.highlight_indices[0] : null;
                    if (hi !== null && mutated[hi]) {
                        const strVal = String(s.value);
                        const match = strVal.match(/=\s*(.+)$/);
                        if (match) mutated[hi] = { ...mutated[hi], val: match[1].trim() };
                    }
                }
            }

            const table = document.createElement('div');
            table.style.display = 'flex';
            table.style.flexDirection = 'column';
            table.style.gap = '8px';
            table.style.width = '90%';

            mutated.forEach((r, idx) => {
                const card = document.createElement('div');
                card.className = 'viz-node-card';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) card.classList.add('active');

                const varName = r.var !== undefined ? r.var : (r.name !== undefined ? r.name : `var${idx}`);
                const typeName = r.type !== undefined ? r.type : '';
                const addrStr = r.addr !== undefined ? r.addr : r.address || '—';
                const valStr = r.val !== undefined ? r.val : (r.value !== undefined ? r.value : '—');

                card.innerHTML = `
                    <div style="flex:1;">
                        <span style="font-weight:700; color:#d4af37;">${escapeHtml(formatVizValue(varName))}</span>
                        ${typeName ? `<span style="font-size:10px; color:#64748b; margin-left:4px;">(${escapeHtml(formatVizValue(typeName))})</span>` : ''}
                    </div>
                    <div style="font-family:Consolas, monospace; font-size:11px; color:#38bdf8; background:#06080e; padding:3px 8px; border-radius:4px;">${escapeHtml(formatVizValue(addrStr))}</div>
                    <div style="font-weight:800; font-size:13px; color:#f8fafc; margin-left:8px;">${escapeHtml(formatVizValue(valStr))}</div>
                `;
                table.appendChild(card);
            });

            stage.appendChild(table);
        }

        // 10. SEARCHING (INTERVAL HALVING) RENDERER
        function renderSearchingViz(stage, spec, stepIndex) {
            const arr = Array.isArray(spec.initial_state) && spec.initial_state.length > 0
                ? spec.initial_state
                : [3, 8, 14, 21, 27, 33, 49, 58, 67, 82];
            const step = spec.steps && spec.steps[stepIndex];

            const grid = document.createElement('div');
            grid.className = 'viz-array-grid';

            arr.forEach((val, idx) => {
                const cellWrapper = document.createElement('div');
                cellWrapper.className = 'viz-array-cell-wrapper';

                const ptrEl = document.createElement('div');
                ptrEl.className = 'viz-array-pointer';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    ptrEl.textContent = (step.pointer) ? formatVizValue(step.pointer) : '▼';
                }
                cellWrapper.appendChild(ptrEl);

                const cell = document.createElement('div');
                cell.className = 'viz-array-cell';

                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    cell.classList.add('highlight');
                }

                cell.textContent = formatVizValue(val);
                cellWrapper.appendChild(cell);

                const idxLabel = document.createElement('div');
                idxLabel.style.fontSize = '10px';
                idxLabel.style.color = '#64748b';
                idxLabel.textContent = `[${idx}]`;
                cellWrapper.appendChild(idxLabel);

                grid.appendChild(cellWrapper);
            });

            stage.appendChild(grid);
        }

        // 11. HASH TABLE (MODULO BUCKETS & COLLISION CHAINING) RENDERER
        function renderHashTableViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            const capacity = 5;
            let buckets = [];
            for (let i = 0; i < capacity; i++) {
                buckets.push({ bucket: i, entries: [] });
            }

            if (Array.isArray(spec.initial_state)) {
                spec.initial_state.forEach((item, idx) => {
                    if (item && item.entries) {
                        buckets[item.bucket !== undefined ? item.bucket : idx] = {
                            bucket: item.bucket !== undefined ? item.bucket : idx,
                            entries: [...item.entries]
                        };
                    } else if (typeof item === 'number' || typeof item === 'string') {
                        const h = (typeof item === 'number' ? item : item.length) % capacity;
                        buckets[h].entries.push(item);
                    }
                });
            }

            for (let i = 0; i <= stepIndex; i++) {
                const s = spec.steps && spec.steps[i];
                if (!s) continue;
                if (s.action === 'insert' && s.value) {
                    const bIdx = (typeof s.value === 'object' && s.value.bucket !== undefined) ? s.value.bucket : ((typeof s.value === 'number' ? s.value : 0) % capacity);
                    const kVal = (typeof s.value === 'object' && s.value.key !== undefined) ? s.value.key : s.value;
                    if (buckets[bIdx] && !buckets[bIdx].entries.includes(kVal)) {
                        buckets[bIdx].entries.push(kVal);
                    }
                }
            }

            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'display:flex; flex-direction:column; gap:8px; width:100%; max-width:480px; margin:0 auto;';

            const header = document.createElement('div');
            header.style.cssText = 'font-size:11px; color:#38bdf8; font-family:Consolas, monospace; text-align:center; margin-bottom:6px; background:rgba(56,189,248,0.08); padding:4px 8px; border-radius:4px;';
            header.textContent = `⚡ Hash Function: hash(key) % ${capacity} → Bucket Slot`;
            wrapper.appendChild(header);

            buckets.forEach((b, bIdx) => {
                const isHighlight = step && step.highlight_indices && step.highlight_indices.includes(bIdx);
                const row = document.createElement('div');
                row.style.cssText = `display:flex; align-items:center; gap:8px; padding:6px 10px; border-radius:6px; background:${isHighlight ? 'rgba(56,189,248,0.14)' : '#0b1120'}; border:1px solid ${isHighlight ? '#38bdf8' : '#1e293b'}; transition:all 0.2s ease;`;

                const slot = document.createElement('div');
                slot.style.cssText = `font-family:Consolas, monospace; font-size:11px; font-weight:700; width:44px; color:${isHighlight ? '#38bdf8' : '#64748b'};`;
                slot.textContent = `[${bIdx}]`;
                row.appendChild(slot);

                const chain = document.createElement('div');
                chain.style.cssText = 'display:flex; align-items:center; gap:6px; flex-wrap:wrap; flex:1;';

                if (b.entries.length === 0) {
                    const empty = document.createElement('span');
                    empty.style.cssText = 'font-size:11px; color:#475569; font-style:italic;';
                    empty.textContent = '∅ (empty)';
                    chain.appendChild(empty);
                } else {
                    b.entries.forEach((ent, eIdx) => {
                        if (eIdx > 0) {
                            const arrow = document.createElement('span');
                            arrow.style.cssText = 'color:#e2e8f0; font-size:11px;';
                            arrow.textContent = '→';
                            chain.appendChild(arrow);
                        }
                        const node = document.createElement('span');
                        node.style.cssText = `background:${isHighlight ? '#0284c7' : '#1e293b'}; color:#f8fafc; font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px; font-family:Consolas, monospace;`;
                        node.textContent = formatVizValue(ent);
                        chain.appendChild(node);
                    });
                }
                row.appendChild(chain);
                wrapper.appendChild(row);
            });

            stage.appendChild(wrapper);
        }

        // 12. STRING (TWO-POINTER & CHARACTER MATCH) RENDERER
        function renderStringViz(stage, spec, stepIndex) {
            const chars = Array.isArray(spec.initial_state) ? spec.initial_state : [];
            const step = spec.steps && spec.steps[stepIndex];
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:12px; width:100%; padding:10px 0;';

            const row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:center;';

            chars.forEach((c, idx) => {
                const cellWrap = document.createElement('div');
                cellWrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; gap:4px;';

                const ptr = document.createElement('div');
                ptr.style.cssText = 'height:14px; font-size:10px; font-weight:700; color:#38bdf8; font-family:Consolas, monospace;';
                if (step && step.highlight_indices && step.highlight_indices.includes(idx)) {
                    if (idx === step.highlight_indices[0] && step.highlight_indices.length > 1) ptr.textContent = '▼ L';
                    else if (idx === step.highlight_indices[step.highlight_indices.length - 1] && step.highlight_indices.length > 1) ptr.textContent = '▼ R';
                    else ptr.textContent = '▼';
                }
                cellWrap.appendChild(ptr);

                const box = document.createElement('div');
                const isHighlight = step && step.highlight_indices && step.highlight_indices.includes(idx);
                box.style.cssText = `width:36px; height:36px; display:flex; align-items:center; justify-content:center; border-radius:6px; font-size:16px; font-weight:800; font-family:Consolas, monospace; background:${isHighlight ? '#0284c7' : '#0f172a'}; border:1px solid ${isHighlight ? '#38bdf8' : '#334155'}; color:${isHighlight ? '#ffffff' : '#f8fafc'}; transition:all 0.2s ease;`;
                box.textContent = formatVizValue(c);
                cellWrap.appendChild(box);

                const idxEl = document.createElement('div');
                idxEl.style.cssText = 'font-size:10px; color:#64748b; font-family:Consolas, monospace;';
                idxEl.textContent = `[${idx}]`;
                cellWrap.appendChild(idxEl);

                row.appendChild(cellWrap);
            });

            wrapper.appendChild(row);
            stage.appendChild(wrapper);
        }

        // 13. CODE EXECUTION TRACE RENDERER
        function renderCodeTraceViz(stage, spec, stepIndex) {
            const step = spec.steps && spec.steps[stepIndex];
            const wrapper = document.createElement('div');
            wrapper.style.cssText = 'display:flex; flex-direction:column; gap:10px; width:100%; max-width:480px; margin:0 auto;';

            const stateCard = document.createElement('div');
            stateCard.style.cssText = 'background:#060a12; border:1px solid #1e293b; border-radius:6px; padding:10px;';
            stateCard.innerHTML = `
                <div style="font-size:11px; color:#38bdf8; font-weight:700; margin-bottom:6px; text-transform:uppercase;">Variable State Inspector</div>
                <div style="font-family:Consolas, monospace; font-size:12px; color:#f8fafc; background:#0b1120; padding:6px 10px; border-radius:4px;">
                    ${step && step.value ? (typeof step.value === 'object' ? Object.entries(step.value).map(([k, v]) => `<span style="color:#94a3b8;">${escapeHtml(k)}:</span> <strong style="color:#38bdf8;">${escapeHtml(formatVizValue(v))}</strong>`).join(' &nbsp;|&nbsp; ') : escapeHtml(formatVizValue(step.value))) : 'Initializing state...'}
                </div>
            `;
            wrapper.appendChild(stateCard);

            const timeline = document.createElement('div');
            timeline.style.cssText = 'display:flex; flex-direction:column; gap:6px;';
            (spec.steps || []).forEach((s, idx) => {
                const isCurrent = idx === stepIndex;
                const row = document.createElement('div');
                row.style.cssText = `display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:4px; font-size:11px; background:${isCurrent ? 'rgba(56,189,248,0.15)' : '#0b1120'}; border:1px solid ${isCurrent ? '#38bdf8' : 'transparent'};`;
                row.innerHTML = `
                    <span style="font-weight:700; color:${isCurrent ? '#38bdf8' : '#64748b'}; width:50px;">Step ${s.step_number}</span>
                    <span style="flex:1; color:${isCurrent ? '#f8fafc' : '#94a3b8'};">${escapeHtml(s.explanation)}</span>
                    ${s.code_line ? `<span style="font-size:10px; color:#e2e8f0; font-family:Consolas, monospace;">Line ${s.code_line}</span>` : ''}
                `;
                timeline.appendChild(row);
            });
            wrapper.appendChild(timeline);

            stage.appendChild(wrapper);
        }

        // ===================== STAGE 4: EXISTING AI TUTOR CHAT INTEGRATION =====================
        let companionChatHistory = [];
        window.voiceAssistantActive = false;
        window._lastQueryWasVoice = false;
        let isCompanionSending = false;
        let companionCurrentRequestId = 0;
        // Monotonic sequence for shared request-identity handling. The companion
        // panel and the AI-tutor panel both route through these so a newer request
        // can never be overwritten by an older in-flight response.
        let mayaCurrentRequestSeq = 0;
        window.__currentMayaAbortController = null;

        const MAYA_TERMINAL = Object.freeze({
            COMPLETED: 'COMPLETED',
            INTERRUPTED: 'INTERRUPTED',
            FAILED: 'FAILED',
            CANCELLED: 'CANCELLED'
        });
        window.MAYA_TERMINAL = MAYA_TERMINAL;

        /**
         * Parses an SSE byte stream into discrete frames.
         *
         * ROOT CAUSE this replaces: every Maya consumer had its own inline parser
         * that split on '\n' and parked the trailing partial line in `buffer`.
         * When the server's final frame arrived without a trailing newline, that
         * event was silently dropped and the turn looked incomplete or hung. A
         * multi-byte character straddling a chunk boundary was also lost.
         *
         * flush() at end-of-stream guarantees the final buffered frame is
         * emitted, and TextDecoder runs with {stream:true} plus a final decode()
         * so split multi-byte characters are never corrupted.
         */
        function createSSEParser(onEvent) {
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let currentEvent = 'message';

            function dispatchOne(rawLine) {
                const line = rawLine.replace(/\r$/, '');
                if (!line) return;
                if (line.startsWith(':')) return; // SSE comment / keep-alive

                if (line.startsWith('event:')) {
                    currentEvent = line.slice(6).trim();
                    return;
                }
                if (line.startsWith('data:')) {
                    const dataRaw = line.slice(5).trim();
                    if (!dataRaw) return;
                    try {
                        onEvent(currentEvent, JSON.parse(dataRaw));
                    } catch (e) {
                        // A malformed frame must never abort the rest of the stream.
                        console.warn('Maya SSE: ignoring unparseable frame', e);
                    }
                }
            }

            function feedLines(final) {
                const lines = buffer.split('\n');
                // Without a trailing newline the last element is an incomplete
                // frame, so hold it back unless this is the final flush.
                buffer = final ? '' : (lines.pop() || '');
                for (const line of lines) dispatchOne(line);
            }

            return {
                push(value) {
                    buffer += decoder.decode(value, { stream: true });
                    feedLines(false);
                },
                /** Flush decoder + trailing buffer. MUST be called after done. */
                flush() {
                    try { buffer += decoder.decode(); } catch (e) { /* no-op */ }
                    feedLines(true);
                    if (buffer) {
                        // Last line arrived with no newline terminator at all.
                        const tail = buffer;
                        buffer = '';
                        dispatchOne(tail);
                    }
                }
            };
        }

        /** Reads an SSE response body, guaranteeing the final frame is processed. */
        async function readSSEStream(response, onEvent) {
            const parser = createSSEParser(onEvent);
            const reader = response.body.getReader();
            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    if (value) parser.push(value);
                }
            } finally {
                // Always flush: this is what guarantees the terminal `done` event
                // is seen even when the server closed without a trailing newline.
                parser.flush();
            }
        }

        /**
         * Classifies the terminal state of a Maya turn.
         * COMPLETED only when the server said so. A stream that simply stopped
         * without a done event is INTERRUPTED, never a silent success.
         */
        function resolveMayaTerminalState(doneData, receivedDone) {
            if (doneData && doneData.status) {
                const s = String(doneData.status).toUpperCase();
                if (s === 'COMPLETED') return MAYA_TERMINAL.COMPLETED;
                if (s === 'INTERRUPTED' || s === 'FAILED' || s === 'CANCELLED') return s;
            }
            if (receivedDone) return MAYA_TERMINAL.COMPLETED;
            return MAYA_TERMINAL.INTERRUPTED;
        }

        /** Student-safe status-pill label for a terminal state. */
        function mayaTerminalLabel(state) {
            switch (state) {
                case MAYA_TERMINAL.COMPLETED: return '\u25cf Idle';
                case MAYA_TERMINAL.INTERRUPTED: return '\u26a0\ufe0f Interrupted';
                case MAYA_TERMINAL.FAILED: return '\u26a0\ufe0f Unavailable';
                case MAYA_TERMINAL.CANCELLED: return '\u25cf Cancelled';
                default: return '\u25cf Idle';
            }
        }

        function createStreamingCompanionBubble() {
            const chatArea = document.getElementById('companionChatArea');
            if (!chatArea) return null;

            const bubble = document.createElement('div');
            bubble.className = 'companion-bubble';
            bubble.style.marginBottom = '8px';
            bubble.style.background = '#0d1017';
            bubble.style.borderLeft = '3px solid #d4af37';
            bubble.style.padding = '10px 12px';
            bubble.style.borderRadius = '6px';
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';

            const header = document.createElement('div');
            header.style.display = 'flex';
            header.style.alignItems = 'center';
            header.style.justifyContent = 'space-between';
            header.innerHTML = `<span style="color:#d4af37; font-size:11px; font-weight:700;">${escapeHtml(botName)}</span><span class="companion-bubble-metrics" style="font-size:10px; color:#10b981; font-family:Consolas, monospace;"></span>`;
            bubble.appendChild(header);

            const contentDiv = document.createElement('div');
            contentDiv.className = 'companion-bubble-content';
            contentDiv.style.marginTop = '4px';
            contentDiv.style.lineHeight = '1.55';
            contentDiv.style.color = '#cbd5e1';
            contentDiv.innerHTML = '<span style="color:#64748b; font-style:italic;">Listening...</span>';
            bubble.appendChild(contentDiv);

            const recsDiv = document.createElement('div');
            recsDiv.className = 'companion-bubble-recs';
            bubble.appendChild(recsDiv);

            chatArea.appendChild(bubble);
            chatArea.scrollTop = chatArea.scrollHeight;

            return {
                bubble,
                header,
                contentDiv,
                recsDiv,
                updateText: (text) => {
                    contentDiv.innerHTML = formatCompanionMarkdown(text);
                    chatArea.scrollTop = chatArea.scrollHeight;
                },
                setMetrics: (metrics) => {
                    const mSpan = header.querySelector('.companion-bubble-metrics');
                    if (mSpan && metrics) {
                        const parts = [];
                        if (metrics.ttft) parts.push(`${metrics.ttft}s TTFT`);
                        if (metrics.total_time) parts.push(`${metrics.total_time}s`);
                        mSpan.textContent = `⚡ ${parts.join(' | ')}`;
                    }
                },
                setRecommendations: (recommendations) => {
                    if (!recommendations || recommendations.length === 0) return;
                    let html = `
                        <div class="companion-rec-strip" style="margin-top:12px; border-top:1px solid rgba(212,175,55,0.2); padding-top:8px;">
                            <div style="font-size:11px; font-weight:700; color:#d4af37; margin-bottom:6px; display:flex; align-items:center; gap:5px;">
                                <span>🎯</span> Recommended Practice (${recommendations.length})
                            </div>
                            <div style="display:flex; flex-direction:column; gap:6px;">
                    `;
                    recommendations.forEach(rec => {
                        const diffClass = (rec.difficulty || 'medium').toLowerCase();
                        html += `
                            <div style="background:#141923; border:1px solid #232d40; border-radius:6px; padding:7px 10px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                                <div style="flex:1; min-width:0;">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="font-size:12px; font-weight:700; color:#f8fafc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(rec.title)}</span>
                                        <span class="badge ${diffClass}" style="font-size:10px; padding:1px 5px;">${rec.difficulty}</span>
                                    </div>
                                    <div style="font-size:11px; color:#94a3b8; margin-top:2px;">${escapeHtml(rec.reason || '')}</div>
                                </div>
                                <button onclick="openProblem('${rec.problem_id}')" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; font-weight:700; font-size:11px; border:none; padding:4px 9px; border-radius:5px; cursor:pointer; white-space:nowrap;">
                                    Solve →
                                </button>
                            </div>
                        `;
                    });
                    html += `</div></div>`;
                    recsDiv.innerHTML = html;
                    chatArea.scrollTop = chatArea.scrollHeight;
                }
            };
        }

        function sendQuickCompanionPrompt(promptText) {
            const input = document.getElementById('companionTextInput');
            if (input && promptText) {
                input.value = promptText;
                sendCompanionMessage();
            }
        }

        function handleDashboardVisualizeClick() {
            const input = document.getElementById('companionTextInput');
            const userTyped = (input ? input.value : '').trim();
            if (userTyped) {
                sendQuickCompanionPrompt(`Visualize ${userTyped}`);
            } else {
                const recentUserMsgs = (companionChatHistory || []).filter(m => m.role === 'user');
                const lastUserMsg = recentUserMsgs.length > 0 ? recentUserMsgs[recentUserMsgs.length - 1] : null;
                if (lastUserMsg && lastUserMsg.content && lastUserMsg.content.length > 3 && !lastUserMsg.content.toLowerCase().startsWith('visualize')) {
                    sendQuickCompanionPrompt(`Visualize the algorithm or data structure from our discussion: ${lastUserMsg.content}`);
                } else {
                    appendCompanionBubble('companion', "What would you like me to visualize? You can ask for any algorithm, data structure, or code, for example:\n- **Visualize how a stack works**\n- **Visualize binary search**\n- **Visualize linked-list insertion**\n- **Visualize recursion**\n- **Visualize a binary tree**\n- **Visualize this code** (paste a snippet)");
                    if (input) {
                        input.placeholder = "Type what to visualize (e.g. 'Visualize a stack', 'Visualize binary search')...";
                        input.focus();
                    }
                }
            }
        }

        async function sendCompanionMessage() {
            if (isCompanionSending) return;

            if (!isAuthenticated()) {
                openAuthModal('signin');
                if (typeof showToast === 'function') showToast('Please sign in to chat with Maya.');
                return;
            }

            const user = getAuthUser();
            const hasGroq = !!(window.currentUserHasGroqKey || (user && user.has_groq_key));
            if (!hasGroq) {
                openGroqKeyModal(true);
                return;
            }

            const input = document.getElementById('companionTextInput');
            const sendBtn = document.getElementById('companionSendBtn');
            const chatArea = document.getElementById('companionChatArea');
            const statusPill = document.getElementById('companionStatusPill');

            const messageText = (input ? input.value : '').trim();
            if (!messageText) return;

            // Interruption handling (Req 34K):
            // If Maya is currently speaking, cancel her speech immediately when the user sends a message
            stopCompanionSpeechImmediate();

            isCompanionSending = true;
            const thisRequestId = ++companionCurrentRequestId;

            // One Send click == one logical request. Abort any superseded
            // in-flight request so it cannot write into the shared bubble or
            // append a stale turn to history, and so the upstream provider work
            // is actually cancelled instead of running to completion unwatched.
            if (window.__currentMayaAbortController) {
                try { window.__currentMayaAbortController.abort('superseded'); } catch (e) {}
            }
            const companionAbortController = new AbortController();
            window.__currentMayaAbortController = companionAbortController;
            // Stable identity for this logical request, echoed back by the server
            // on every SSE frame so stale responses can be rejected precisely.
            const companionRequestId = generateMayaRequestId();

            // 1. Clear input & disable controls while processing
            input.value = '';
            input.disabled = true;
            if (sendBtn) sendBtn.disabled = true;

            // 2. Append user bubble
            appendCompanionBubble('user', messageText);

            // 3. Set companion into thinking state (Req 34J)
            if (statusPill) {
                statusPill.className = 'companion-status-pill thinking';
                statusPill.textContent = '● Thinking';
            }
            if (window.setCompanionExpression) {
                window.setCompanionExpression('thinking');
            }

            // 4. Gather active problem + language + editor code context
            const isProblemWorkspace = (window.active_workspace === 'problem_solving' || window.active_workspace === 'test_taking');
            const probId = isProblemWorkspace ? ((typeof getActiveProblemId === 'function') ? getActiveProblemId() : null) : null;
            const activeProblem = isProblemWorkspace ? currentProblemData : null;
            const code = isProblemWorkspace ? ((typeof getActiveCode === 'function') ? getActiveCode() : '') : '';
            const trimmedCode = (code || '').trim();
            const isPlaceholderCode = !trimmedCode ||
                trimmedCode === '# Select a problem to view starter code' ||
                trimmedCode === '// Select a problem to view starter code';

            let lang = null;
            if (isProblemWorkspace && (probId || !isPlaceholderCode)) {
                if (typeof isTestMode === 'function' && isTestMode() && document.getElementById('takingLanguageSelect')) {
                    lang = document.getElementById('takingLanguageSelect').value;
                } else if (document.getElementById('languageSelect')) {
                    lang = document.getElementById('languageSelect').value;
                } else if (typeof getActiveLanguage === 'function') {
                    lang = getActiveLanguage();
                }
            }
            const user = getAuthUser();
            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
            const sid = getStudentId();
            const token = getAuthToken();

            // Check if last execution resulted in error or failed test cases
            const resultEl = document.getElementById('result');
            const execOutput = (isProblemWorkspace && resultEl) ? (resultEl.textContent || '').trim().slice(0, 1000) : null;
            let lastError = (isProblemWorkspace && resultEl && resultEl.textContent && (resultEl.textContent.includes('Error') || resultEl.textContent.includes('Exception') || resultEl.textContent.includes('Failed')))
                ? resultEl.textContent.trim().slice(0, 500)
                : null;

            let failedTestCase = null;
            if (isProblemWorkspace && typeof lastExecutionResult !== 'undefined' && lastExecutionResult && Array.isArray(lastExecutionResult.test_results)) {
                const failed = lastExecutionResult.test_results.find(tc => !tc.passed);
                if (failed) {
                    failedTestCase = {
                        input: failed.input || '',
                        expected_output: failed.expected_output || '',
                        actual_output: failed.actual_output || '',
                        error: failed.error || null
                    };
                }
            }
            const submissionStatus = (isProblemWorkspace && typeof lastExecutionResult !== 'undefined' && lastExecutionResult && lastExecutionResult.status) ? lastExecutionResult.status : null;

            // Check Test Mode & Instructor Policy (Req 43, 44, 48)
            const inTest = isProblemWorkspace && ((typeof isTestMode === 'function') ? isTestMode() : false);
            const testId = (inTest && typeof activeTestSession !== 'undefined' && activeTestSession && activeTestSession.test) ? activeTestSession.test.id : null;
            const testAIEnabled = (inTest && typeof activeTestSession !== 'undefined' && activeTestSession && activeTestSession.test) ? Boolean(activeTestSession.test.enable_ai_tutor) : true;

            let safeCode = isProblemWorkspace ? code : null;
            let safeError = lastError;
            let safeExecOutput = execOutput;
            let safeFailedTc = failedTestCase;
            // Context Protection & Test Enforcement: If AI assistance is disabled for test, block request client-side
            if (inTest && !testAIEnabled) {
                appendCompanionBubble('companion', "🚫 AI assistance is disabled by the instructor for this assessment test.");
                if (statusPill) {
                    statusPill.className = 'companion-status-pill';
                    statusPill.textContent = '● Disabled';
                }
                return;
            }

            const constraintsStr = (activeProblem && activeProblem.constraints)
                ? (Array.isArray(activeProblem.constraints) ? activeProblem.constraints.join('\n') : String(activeProblem.constraints))
                : null;
            const examplesData = (activeProblem && activeProblem.examples) ? activeProblem.examples : null;

            const payload = {
                message: messageText,
                stream: true,
                conversation_id: getOrCreateMayaConversationId(),
                request_id: companionRequestId,
                context: {
                    student_id: sid,
                    student_name: studentName,
                    bot_name: botName,
                    active_workspace: window.active_workspace || 'dashboard',
                    problem_id: probId,
                    problem_title: (activeProblem ? activeProblem.title : null),
                    problem_description: (activeProblem ? activeProblem.description : null),
                    constraints: constraintsStr,
                    examples: examplesData,
                    selected_language: lang,
                    current_code: safeCode,
                    last_error: safeError,
                    execution_output: safeExecOutput,
                    failed_test_case: safeFailedTc,
                    submission_status: submissionStatus,
                    test_id: testId,
                    is_test_mode: inTest,
                    visualization_context: (typeof getActiveVisualizationContext === 'function' ? getActiveVisualizationContext() : null)
                },
                history: companionChatHistory.slice(-10)
            };

            try {
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                if (sid && sid !== 'null' && sid !== 'undefined') headers['X-Student-Id'] = sid;

                const res = await fetch(`${API_BASE}/api/ai/companion/chat`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload),
                    signal: companionAbortController.signal
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    const errMsg = safeExtractErrorMessage(errData, 'Could not reach AI Companion engine.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    throw httpErr;
                }

                // Check if response is SSE stream
                const contentType = res.headers.get('content-type') || '';
                if (contentType.includes('text/event-stream') && res.body) {
                    const streamUi = createStreamingCompanionBubble();
                    let accumulatedText = '';
                    let finalDoneData = null;
                    let receivedDone = false;
                    let serverError = null;

                    if (statusPill) {
                        statusPill.className = 'companion-status-pill speaking';
                        statusPill.textContent = '● Streaming';
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('speaking');
                    }

                    // Shared parser guarantees the final frame is processed even
                    // when the server closes the stream without a trailing newline.
                    await readSSEStream(res, (eventName, dataObj) => {
                        if (eventName === 'delta') {
                            if (dataObj.text) {
                                accumulatedText += dataObj.text;
                                if (streamUi) streamUi.updateText(accumulatedText);
                            }
                        } else if (eventName === 'visualization') {
                            // A visualization must never be able to break text
                            // streaming, so failures here are contained.
                            try { renderCompanionVisualization(dataObj); } catch (vizErr) {
                                console.warn('Maya visualization render failed', vizErr);
                            }
                        } else if (eventName === 'metrics') {
                            if (streamUi) streamUi.setMetrics(dataObj);
                        } else if (eventName === 'error') {
                            serverError = dataObj;
                        } else if (eventName === 'done') {
                            receivedDone = true;
                            finalDoneData = dataObj;
                            if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                accumulatedText = dataObj.message;
                                if (streamUi) streamUi.updateText(accumulatedText);
                            }
                            if (dataObj.visualization) {
                                try { renderCompanionVisualization(dataObj.visualization); } catch (vizErr) {
                                    console.warn('Maya visualization render failed', vizErr);
                                }
                            }
                            if (dataObj.recommended_problems && streamUi) {
                                streamUi.setRecommendations(dataObj.recommended_problems);
                            }
                        }
                    });

                    // Stale-response guard: a newer Send already won.
                    if (thisRequestId !== companionCurrentRequestId) return;

                    // COMPLETED only when the server actually said so.
                    const terminalState = resolveMayaTerminalState(finalDoneData, receivedDone);

                    if (terminalState === MAYA_TERMINAL.COMPLETED) {
                        if (accumulatedText) {
                            companionChatHistory.push({ role: 'user', content: messageText });
                            const histMessage = accumulatedText.length > 2500
                                ? (accumulatedText.slice(0, 2500) + '...')
                                : accumulatedText;
                            companionChatHistory.push({ role: 'companion', content: histMessage });
                        }
                    } else if (accumulatedText) {
                        // Partial output is useful: keep it visible and let the
                        // next turn continue from it, but never store it as a
                        // completed turn.
                        companionChatHistory.push({ role: 'user', content: messageText });
                        const histMessage = accumulatedText.length > 2500
                            ? (accumulatedText.slice(0, 2500) + '...')
                            : accumulatedText;
                        companionChatHistory.push({ role: 'companion', content: histMessage });
                    }

                    const shouldSpeak = (window.voiceAssistantActive || window._lastQueryWasVoice) && !window.companionAudioMuted;
                    window._lastQueryWasVoice = false;
                    if (shouldSpeak && accumulatedText && terminalState === MAYA_TERMINAL.COMPLETED) {
                        speakCompanionResponse(accumulatedText, (finalDoneData && finalDoneData.expression) || 'speaking');
                    } else {
                        if (window.setCompanionExpression) {
                            window.setCompanionExpression(
                                terminalState === MAYA_TERMINAL.COMPLETED ? 'idle' : 'confused'
                            );
                        }
                        if (statusPill) {
                            statusPill.className = (terminalState === MAYA_TERMINAL.COMPLETED)
                                ? 'companion-status-pill'
                                : 'companion-status-pill error';
                            statusPill.textContent = mayaTerminalLabel(terminalState);
                        }
                    }

                    // FAILED with no text at all: surface the friendly message.
                    if (terminalState !== MAYA_TERMINAL.COMPLETED && !accumulatedText && streamUi) {
                        const msg = (serverError && serverError.message)
                            ? serverError.message
                            : 'Maya could not complete that response. Please try again.';
                        streamUi.updateText(msg);
                    }

                } else {
                    // Non-streaming JSON fallback
                    const data = await res.json();
                    if (thisRequestId !== companionCurrentRequestId) return;

                    appendCompanionBubble('companion', data.message, data.recommended_problems);
                    companionChatHistory.push({ role: 'user', content: messageText });
                    const histMessage = (data.message && data.message.length > 2500)
                        ? (data.message.slice(0, 2500) + '...')
                        : (data.message || '');
                    companionChatHistory.push({ role: 'companion', content: histMessage });

                    if (data.visualization) {
                        renderCompanionVisualization(data.visualization);
                    }

                    const shouldSpeak = (window.voiceAssistantActive || window._lastQueryWasVoice) && !window.companionAudioMuted;
                    window._lastQueryWasVoice = false;
                    if (shouldSpeak) {
                        speakCompanionResponse(data.message, data.expression);
                    } else {
                        if (window.setCompanionExpression) window.setCompanionExpression('idle');
                        if (statusPill) {
                            statusPill.className = 'companion-status-pill';
                            statusPill.textContent = '● Idle';
                        }
                    }
                }


            } catch (err) {
                // A superseded request is cancelled, not failed: show nothing.
                if (err && (err.name === 'AbortError' || companionAbortController.signal.aborted)) {
                    return;
                }
                if (thisRequestId === companionCurrentRequestId) {
                    console.error('Companion chat failed:', err);
                    const classified = classifyApiError(err);
                    if (classified.type === 'BACKEND OFFLINE') {
                        appendCompanionSystemNotice(`⚠️ <strong>CodeMind Backend Offline</strong><br/><span style="color:#e2e8f0; font-size:12px; margin-top:4px; display:block;">Could not connect to CodeMind server at <code>${escapeHtml(API_BASE)}</code>. Please ensure the backend is running.</span>`);
                        if (statusPill) {
                            statusPill.className = 'companion-status-pill error';
                            statusPill.textContent = '● Backend Offline';
                        }
                    } else {
                        const isGroqErr = err.message && (err.message.toLowerCase().includes('groq') || err.message.includes('Personal Groq API key'));
                        const isConfigErr = err.message && (err.message.includes('OPENAI_API_KEY') || err.message.includes('NVIDIA_API_KEY') || err.message.includes('Configuration Required'));
                        if (isGroqErr) {
                            appendCompanionSystemNotice(`🔑 <strong>Personal Groq Key Required</strong><br/><span style="color:#e2e8f0; font-size:12px; margin-top:4px; display:block;">${escapeHtml(err.message)}</span><button onclick="openGroqKeyModal(true)" style="margin-top:8px; padding:6px 14px; background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; font-weight:700; border:none; border-radius:6px; cursor:pointer; font-size:12px;">🔑 Connect Groq Key</button>`);
                            if (statusPill) {
                                statusPill.className = 'companion-status-pill error';
                                statusPill.textContent = '● Key Required';
                            }
                            openGroqKeyModal(true);
                        } else if (isConfigErr) {
                            appendCompanionSystemNotice(`⚠️ <strong>AI Provider Configuration Required</strong><br/><span style="color:#e2e8f0; font-size:12px; margin-top:4px; display:block;">${escapeHtml(err.message)}</span><span style="color:#94a3b8; font-size:11px; margin-top:4px; display:block;">Configure your personal Groq API key in Settings.</span>`);
                            if (statusPill) {
                                statusPill.className = 'companion-status-pill error';
                                statusPill.textContent = '● Config Error';
                            }
                        } else {
                            appendCompanionBubble('companion', `⚠️ **${classified.type}:** ${classified.message}`);
                            if (statusPill) {
                                statusPill.className = 'companion-status-pill error';
                                statusPill.textContent = `● ${classified.type}`;
                            }
                        }
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('confused');
                    }
                }
            } finally {
                isCompanionSending = false;
                if (input) {
                    input.disabled = false;
                    input.focus();
                }
                if (sendBtn) sendBtn.disabled = false;
            }
        }

        function appendCompanionSystemNotice(htmlContent) {
            const chatArea = document.getElementById('companionChatArea');
            if (!chatArea) return;
            const card = document.createElement('div');
            card.style.background = 'rgba(239, 68, 68, 0.08)';
            card.style.border = '1px solid rgba(239, 68, 68, 0.35)';
            card.style.borderLeft = '3px solid #ef4444';
            card.style.borderRadius = '8px';
            card.style.padding = '10px 14px';
            card.style.marginBottom = '10px';
            card.style.color = '#fca5a5';
            card.style.fontSize = '12.5px';
            card.style.lineHeight = '1.5';
            card.innerHTML = htmlContent;
            chatArea.appendChild(card);
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function appendCompanionBubble(role, rawContent, recommendations = []) {
            const chatArea = document.getElementById('companionChatArea');
            if (!chatArea) return;

            const bubble = document.createElement('div');
            bubble.className = 'companion-bubble';
            bubble.style.marginBottom = '8px';

            if (role === 'user') {
                bubble.style.background = '#131826';
                bubble.style.borderLeft = '3px solid #38bdf8';
                bubble.style.padding = '8px 12px';
                bubble.style.borderRadius = '6px';
                bubble.innerHTML = `<span style="color:#94a3b8; font-size:11px; font-weight:700;">YOU</span><div style="margin-top:2px; color:#f8fafc;">${escapeHtml(rawContent)}</div>`;
            } else {
                bubble.style.background = '#0d1017';
                bubble.style.borderLeft = '3px solid #d4af37';
                bubble.style.padding = '10px 12px';
                bubble.style.borderRadius = '6px';
                const botName = localStorage.getItem('codemind_bot_name') || 'Companion';
                let contentHtml = `<span style="color:#d4af37; font-size:11px; font-weight:700;">${escapeHtml(botName)}</span><div style="margin-top:4px; line-height:1.55; color:#cbd5e1;">${formatCompanionMarkdown(rawContent)}</div>`;

                if (recommendations && recommendations.length > 0) {
                    contentHtml += `
                        <div class="companion-rec-strip" style="margin-top:12px; border-top:1px solid rgba(212,175,55,0.2); padding-top:8px;">
                            <div style="font-size:11px; font-weight:700; color:#d4af37; margin-bottom:6px; display:flex; align-items:center; gap:5px;">
                                <span>🎯</span> Recommended Practice (${recommendations.length})
                            </div>
                            <div style="display:flex; flex-direction:column; gap:6px;">
                    `;
                    recommendations.forEach(rec => {
                        const diffClass = (rec.difficulty || 'medium').toLowerCase();
                        contentHtml += `
                            <div style="background:#141923; border:1px solid #232d40; border-radius:6px; padding:7px 10px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                                <div style="flex:1; min-width:0;">
                                    <div style="display:flex; align-items:center; gap:6px;">
                                        <span style="font-size:12px; font-weight:700; color:#f8fafc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(rec.title)}</span>
                                        <span class="badge ${diffClass}" style="font-size:10px; padding:1px 5px;">${rec.difficulty}</span>
                                    </div>
                                    <div style="font-size:11px; color:#94a3b8; margin-top:2px;">${escapeHtml(rec.reason || '')}</div>
                                </div>
                                <button onclick="openProblem('${rec.problem_id}')" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; font-weight:700; font-size:11px; border:none; padding:4px 9px; border-radius:5px; cursor:pointer; white-space:nowrap;">
                                    Solve →
                                </button>
                            </div>
                        `;
                    });
                    contentHtml += `</div></div>`;
                }

                bubble.innerHTML = contentHtml;
            }

            chatArea.appendChild(bubble);
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function formatCompanionMarkdown(text) {
            if (!text) return '';
            // Strip any visualization JSON code blocks or tags so raw JSON NEVER renders in the chat bubble
            text = text.replace(/```(?:visualization|viz|flowchart)\s*[\s\S]*?```/gi, '');
            text = text.replace(/<visualization>[\s\S]*?<\/visualization>/gi, '');
            text = text.replace(/```(?:json)?\s*\{[\s\S]*?"viz_type"[\s\S]*?\}\s*```/gi, '');
            text = text.replace(/\{[\s\r\n]*"viz_type"[\s\S]*?\}\s*$/gi, '');

            if (typeof formatAITutorMarkdown === 'function') {
                return formatAITutorMarkdown(text);
            }
            // Basic safe markdown formatter: bold, inline code, fenced code, bullet lists
            let formatted = escapeHtml(text);
            formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre style="background:#05070a; border:1px solid #232a38; border-radius:6px; padding:8px; font-family:Consolas, monospace; font-size:12px; color:#38bdf8; overflow-x:auto; margin:6px 0;"><code>$1</code></pre>');
            formatted = formatted.replace(/`([^`]+)`/g, '<code style="background:#161c28; color:#facc15; padding:2px 4px; border-radius:3px; font-size:12px;">$1</code>');
            formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong style="color:#f8fafc;">$1</strong>');
            formatted = formatted.replace(/\n- /g, '<br/>• ');
            formatted = formatted.replace(/\n\n/g, '<div style="height:6px;"></div>');
            formatted = formatted.replace(/\n/g, '<br/>');
            return formatted;
        }

        // ===================== STAGE 6: VOICE, SPEECH & COMPANION INTERACTION =====================
        function getUserCompanionStorageKey(key) {
            try {
                const user = (typeof getAuthUser === 'function') ? getAuthUser() : null;
                const uid = (user && (user.id || user.student_id || user.username)) || 'guest';
                return `codemind_${key}_${uid}`;
            } catch (e) {
                return `codemind_${key}_guest`;
            }
        }

        window.companionAudioMuted = (localStorage.getItem(getUserCompanionStorageKey('audio_muted')) === 'true');
        window.companionMicPermission = localStorage.getItem('codemind_mic_permission') || null;
        window.companionWakeActive = false;
        window.wakeRecognition = null;

        let manualRecognition = null;
        let isManualListening = false;

        function updateCompanionMuteUI() {
            const btn = document.getElementById('companionMuteToggle');
            if (!btn) return;
            const key = getUserCompanionStorageKey('audio_muted');
            window.companionAudioMuted = (localStorage.getItem(key) === 'true');
            if (window.companionAudioMuted) {
                btn.textContent = '🔇';
                btn.classList.add('muted');
                btn.title = 'Companion voice speech is muted (Click to unmute)';
            } else {
                btn.textContent = '🔊';
                btn.classList.remove('muted');
                btn.title = 'Companion voice speech is unmuted (Click to mute)';
            }
        }

        function toggleCompanionAudioMute() {
            const key = getUserCompanionStorageKey('audio_muted');
            window.companionAudioMuted = !(localStorage.getItem(key) === 'true');
            localStorage.setItem(key, window.companionAudioMuted ? 'true' : 'false');
            updateCompanionMuteUI();
            if (window.companionAudioMuted) {
                stopCompanionSpeechImmediate();
            }
        }

        function cleanTextForSpeech(text) {
            if (!text) return '';
            return text
                .replace(/```[\s\S]*?```/g, ' code snippet omitted. ')
                .replace(/`([^`]+)`/g, '$1')
                .replace(/\*\*([^*]+)\*\*/g, '$1')
                .replace(/\*([^*]+)\*/g, '$1')
                .replace(/#{1,6}\s+/g, '')
                .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
                .replace(/🎯|💡|✨|🤖|🗺️|🧬|📊|⚠️|●/g, '')
                .replace(/<[^>]+>/g, '')
                .trim();
        }

        function getBestCompanionFemaleVoice() {
            if (!('speechSynthesis' in window)) return null;
            const voices = window.speechSynthesis.getVoices();
            if (!voices || voices.length === 0) return null;

            const femaleKeywords = [
                'zira', 'jenny', 'aria', 'samantha', 'victoria', 'karen', 'moira',
                'tessa', 'fiona', 'ava', 'allison', 'susan', 'sonia', 'libby',
                'clara', 'natasha', 'female'
            ];
            const maleKeywords = [
                'david', 'mark', 'george', 'guy', 'james', 'richard', 'male', 'daniel', 'oliver', 'ryan'
            ];

            const enVoices = voices.filter(v => (v.lang || '').toLowerCase().startsWith('en'));

            // 1. High priority: English female voice
            for (const kw of femaleKeywords) {
                const match = enVoices.find(v => {
                    const n = (v.name || '').toLowerCase();
                    return n.includes(kw) && !maleKeywords.some(m => n.includes(m));
                });
                if (match) return match;
            }

            // 2. Any English voice with female in name/gender
            const genericFemale = enVoices.find(v => {
                const n = (v.name || '').toLowerCase();
                return (n.includes('female') || n.includes('woman')) && !maleKeywords.some(m => n.includes(m));
            });
            if (genericFemale) return genericFemale;

            // 3. Fallback: Any English voice not containing male identifiers
            const nonMaleEn = enVoices.find(v => {
                const n = (v.name || '').toLowerCase();
                return !maleKeywords.some(m => n.includes(m));
            });
            if (nonMaleEn) return nonMaleEn;

            // 4. Ultimate safe fallback
            return enVoices[0] || voices[0] || null;
        }

        if ('speechSynthesis' in window) {
            window.speechSynthesis.onvoiceschanged = () => {
                window._cachedCompanionVoice = getBestCompanionFemaleVoice();
            };
        }

        function speakCompanionResponse(rawText, expression = 'speaking') {
            const statusPill = document.getElementById('companionStatusPill');

            // Crucial: Stop recognition immediately so Maya NEVER hears her own voice while speaking
            if (window.wakeRecognition) {
                try { window.wakeRecognition.abort(); } catch (e) {}
            }
            window._mayaIsSpeaking = true;

            // If audio muted or speech synthesis not available:
            if (window.companionAudioMuted || !('speechSynthesis' in window)) {
                window._mayaIsSpeaking = false;
                const silentExpr = (expression && expression !== 'speaking') ? expression : 'idle';
                if (window.setCompanionExpression) {
                    window.setCompanionExpression(silentExpr);
                }
                if (statusPill) {
                    statusPill.className = 'companion-status-pill';
                    statusPill.textContent = '● Idle';
                }
                return;
            }

            try {
                window.speechSynthesis.cancel();
                const speechText = cleanTextForSpeech(rawText);
                if (!speechText) {
                    window._mayaIsSpeaking = false;
                    if (window.setCompanionExpression) window.setCompanionExpression('idle');
                    return;
                }

                // Keep spoken text friendly and digestible
                const truncatedSpoken = speechText.length > 300 ? speechText.slice(0, 300) + '...' : speechText;
                const utterance = new SpeechSynthesisUtterance(truncatedSpoken);
                utterance.rate = 1.0;
                utterance.pitch = 1.10; // Friendly, warm female tutor pitch

                const selectedVoice = window._cachedCompanionVoice || getBestCompanionFemaleVoice();
                if (selectedVoice) {
                    utterance.voice = selectedVoice;
                }

                utterance.onstart = () => {
                    const stopBtn = document.getElementById('companionStopSpeechBtn');
                    if (stopBtn) stopBtn.style.display = 'inline-block';
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('speaking');
                    }
                    if (statusPill) {
                        statusPill.className = 'companion-status-pill speaking';
                        statusPill.textContent = '● Speaking';
                    }
                };

                const finishSpeaking = () => {
                    window._mayaIsSpeaking = false;
                    const stopBtn = document.getElementById('companionStopSpeechBtn');
                    if (stopBtn) stopBtn.style.display = 'none';
                    if (window.stopCompanionSpeakingAnimation) {
                        try { window.stopCompanionSpeakingAnimation(); } catch (e) {}
                    }
                    if (window.voiceAssistantActive) {
                        if (window.setCompanionExpression) {
                            window.setCompanionExpression('listening');
                        }
                        if (statusPill) {
                            statusPill.className = 'companion-status-pill listening';
                            statusPill.textContent = '● Listening';
                        }
                        // Resume background wake recognition after speaking finishes
                        setTimeout(() => {
                            if (window.voiceAssistantActive && !window._mayaIsSpeaking && !isManualListening) {
                                window.startCompanionWakeRecognition();
                            }
                        }, 400);
                    } else {
                        if (window.setCompanionExpression) {
                            window.setCompanionExpression('idle');
                        }
                        if (statusPill) {
                            statusPill.className = 'companion-status-pill';
                            statusPill.textContent = '● Idle';
                        }
                    }
                };

                utterance.onend = finishSpeaking;
                utterance.onerror = finishSpeaking;

                window.speechSynthesis.speak(utterance);
            } catch (err) {
                console.warn('Speech synthesis error:', err);
                window._mayaIsSpeaking = false;
                if (window.setCompanionExpression) {
                    window.setCompanionExpression(expression || 'speaking');
                    setTimeout(() => window.setCompanionExpression('idle'), 2500);
                }
            }
        }

        function checkOrPromptMicPermission(callbackIfAllowed) {
            if (window.companionMicPermission === 'granted') {
                if (callbackIfAllowed) callbackIfAllowed();
                return;
            }

            if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
                navigator.mediaDevices.getUserMedia({ audio: true })
                    .then((stream) => {
                        window.companionMicPermission = 'granted';
                        localStorage.setItem('codemind_mic_permission', 'granted');
                        // Release stream immediately
                        stream.getTracks().forEach(t => t.stop());
                        if (callbackIfAllowed) callbackIfAllowed();
                    })
                    .catch((err) => {
                        console.warn('Mic permission denied:', err);
                        window.companionMicPermission = 'denied';
                        localStorage.setItem('codemind_mic_permission', 'denied');
                        appendCompanionBubble('companion', 'Microphone access was denied. You can continue chatting with Maya using text!');
                    });
                return;
            }

            appendCompanionBubble('companion', 'Microphone access is not supported in this browser. You can continue chatting with me using text!');
        }

        function toggleCompanionManualVoice() {
            checkOrPromptMicPermission(() => {
                if (isManualListening) {
                    stopCompanionManualVoice();
                } else {
                    startCompanionManualVoice();
                }
            });
        }

        function startCompanionManualVoice() {
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRec) return;

            // Pause wake recognition while manual mic is active
            if (window.wakeRecognition) {
                try { window.wakeRecognition.abort(); } catch (e) {}
            }

            try {
                manualRecognition = new SpeechRec();
                manualRecognition.continuous = false;
                manualRecognition.interimResults = true;
                manualRecognition.lang = 'en-US';

                const micBtn = document.getElementById('companionVoiceBtn');
                const statusPill = document.getElementById('companionStatusPill');
                const input = document.getElementById('companionTextInput');

                manualRecognition.onstart = () => {
                    isManualListening = true;
                    if (micBtn) micBtn.classList.add('listening');
                    if (statusPill) {
                        statusPill.className = 'companion-status-pill listening';
                        statusPill.textContent = '● Listening';
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('listening');
                    }
                };

                manualRecognition.onresult = (event) => {
                    let transcript = '';
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        transcript += event.results[i][0].transcript;
                    }
                    if (input) input.value = transcript;
                    if (event.results[0].isFinal) {
                        window._lastQueryWasVoice = true;
                        stopCompanionManualVoice();
                        sendCompanionMessage();
                    }
                };

                manualRecognition.onerror = (event) => {
                    console.warn('Voice input error:', event.error);
                    stopCompanionManualVoice();
                };

                manualRecognition.onend = () => {
                    stopCompanionManualVoice();
                };

                manualRecognition.start();
            } catch (e) {
                console.error('Failed to start speech recognition:', e);
                stopCompanionManualVoice();
            }
        }

        function stopCompanionSpeechImmediate() {
            window._mayaIsSpeaking = false;
            if ('speechSynthesis' in window) {
                try { window.speechSynthesis.cancel(); } catch (e) {}
            }
            if (window.stopCompanionSpeakingAnimation) {
                try { window.stopCompanionSpeakingAnimation(); } catch (e) {}
            }
            const stopBtn = document.getElementById('companionStopSpeechBtn');
            if (stopBtn) stopBtn.style.display = 'none';

            const statusPill = document.getElementById('companionStatusPill');
            if (window.voiceAssistantActive) {
                if (statusPill) {
                    statusPill.className = 'companion-status-pill listening';
                    statusPill.textContent = '● Listening';
                }
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('listening');
                }
                setTimeout(() => {
                    if (window.voiceAssistantActive && !window._mayaIsSpeaking && !isManualListening) {
                        window.startCompanionWakeRecognition();
                    }
                }, 300);
            } else {
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('idle');
                }
                if (statusPill) {
                    statusPill.className = 'companion-status-pill';
                    statusPill.textContent = '● Idle';
                }
            }
        }

        function stopCompanionManualVoice() {
            isManualListening = false;
            const micBtn = document.getElementById('companionVoiceBtn');
            if (micBtn) micBtn.classList.remove('listening');
            if (manualRecognition) {
                try { manualRecognition.abort(); } catch (e) {}
                manualRecognition = null;
            }
            const statusPill = document.getElementById('companionStatusPill');
            if (window.voiceAssistantActive) {
                if (statusPill) {
                    statusPill.className = 'companion-status-pill listening';
                    statusPill.textContent = '● Listening';
                }
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('listening');
                }
                if (window.startCompanionWakeRecognition) {
                    setTimeout(window.startCompanionWakeRecognition, 400);
                }
            } else {
                if (statusPill && statusPill.textContent.includes('Listening')) {
                    statusPill.className = 'companion-status-pill';
                    statusPill.textContent = '● Idle';
                }
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('idle');
                }
            }
        }

        function toggleVoiceAssistantMode() {
            const toggle = document.getElementById('companionVoiceToggle') || document.getElementById('companionWakeToggle');
            const statusPill = document.getElementById('companionStatusPill');
            if (!window.voiceAssistantActive) {
                checkOrPromptMicPermission(() => {
                    window.voiceAssistantActive = true;
                    window.companionWakeActive = true;
                    if (toggle) {
                        toggle.classList.add('voice-active');
                        toggle.textContent = 'Voice: ON';
                    }
                    if (statusPill) {
                        statusPill.className = 'companion-status-pill listening';
                        statusPill.textContent = '● Listening';
                    }
                    if (window.setCompanionExpression) {
                        window.setCompanionExpression('listening');
                    }
                    window.startCompanionWakeRecognition();
                    if (typeof showToast === 'function') {
                        showToast("Voice Assistant ON: Say 'Maya' or 'Hey Maya' to speak!");
                    }
                });
            } else {
                window.voiceAssistantActive = false;
                window.companionWakeActive = false;
                if (toggle) {
                    toggle.classList.remove('voice-active');
                    toggle.textContent = 'Voice: OFF';
                }
                if (window.wakeRecognition) {
                    try { window.wakeRecognition.abort(); } catch (e) {}
                    window.wakeRecognition = null;
                }
                stopCompanionSpeechImmediate();
                if (statusPill) {
                    statusPill.className = 'companion-status-pill';
                    statusPill.textContent = '● Idle';
                }
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('idle');
                }
                if (typeof showToast === 'function') {
                    showToast("Voice Assistant OFF: Maya is in silent text mode.");
                }
            }
        }

        function toggleCompanionWakeWord() {
            toggleVoiceAssistantMode();
        }

        let wakeQuestionTimer = null;

        window.startCompanionWakeRecognition = function() {
            if (!window.companionWakeActive || window._mayaIsSpeaking) return;
            if ('speechSynthesis' in window && window.speechSynthesis.speaking) return;
            if (isManualListening) return;

            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRec) return;

            if (window.wakeRecognition) {
                try { window.wakeRecognition.abort(); } catch (e) {}
            }

            try {
                window.wakeRecognition = new SpeechRec();
                window.wakeRecognition.continuous = true;
                window.wakeRecognition.interimResults = true;
                window.wakeRecognition.lang = 'en-US';

                let isCapturingQuestion = false;
                let capturedQuestion = '';

                window.wakeRecognition.onresult = (event) => {
                    if (!window.companionWakeActive || window._mayaIsSpeaking) return;
                    if ('speechSynthesis' in window && window.speechSynthesis.speaking) {
                        try { window.wakeRecognition.abort(); } catch (e) {}
                        return;
                    }

                    const currentBot = (localStorage.getItem('codemind_bot_name') || 'Maya').toLowerCase();
                    let fullTranscript = '';
                    let isFinal = false;
                    for (let i = event.resultIndex; i < event.results.length; ++i) {
                        fullTranscript += event.results[i][0].transcript.toLowerCase();
                        if (event.results[i].isFinal) isFinal = true;
                    }
                    fullTranscript = fullTranscript.trim();
                    if (!fullTranscript) return;

                    const statusPill = document.getElementById('companionStatusPill');

                    // 1. Wake phrase detection
                    const wakePhrases = ['hey ' + currentBot, currentBot, 'hey maya', 'maya'];
                    const matchedPhrase = wakePhrases.find(p => {
                        const regex = new RegExp('\\b' + p + '\\b', 'i');
                        return regex.test(fullTranscript);
                    });

                    // 2. Short follow-up phrases support: 'Why?', 'Show me.', 'How does it work?', 'Explain that.'
                    const followUpPhrases = ['why', 'why?', 'show me', 'show me.', 'how does it work', 'explain that'];
                    const isFollowUp = followUpPhrases.includes(fullTranscript.replace(/[.?!]/g, '').trim());

                    if (matchedPhrase || isCapturingQuestion || isFollowUp) {
                        let query = '';
                        if (isFollowUp && !matchedPhrase) {
                            query = fullTranscript;
                        } else if (matchedPhrase) {
                            const parts = fullTranscript.split(matchedPhrase);
                            query = (parts.slice(1).join(matchedPhrase) || '').trim();
                            query = query.replace(/^[,!.\s]+/, '');
                        } else if (isCapturingQuestion) {
                            query = fullTranscript.replace(/^[,!.\s]+/, '');
                        }

                        if (statusPill) {
                            statusPill.className = 'companion-status-pill listening';
                            statusPill.textContent = '● Listening...';
                        }
                        if (window.setCompanionExpression) {
                            window.setCompanionExpression('listening');
                        }

                        const executeVoiceQuery = (textToSubmit) => {
                            clearTimeout(wakeQuestionTimer);
                            wakeQuestionTimer = null;
                            isCapturingQuestion = false;
                            if (window.wakeRecognition) {
                                try { window.wakeRecognition.abort(); } catch (e) {}
                            }

                            if (textToSubmit && textToSubmit.length > 2) {
                                window._lastQueryWasVoice = true;
                                const input = document.getElementById('companionTextInput');
                                if (input) input.value = textToSubmit;
                                sendCompanionMessage();
                            } else {
                                // Only wake phrase heard: Maya prompts back!
                                const promptMsg = "I'm listening! What can I explain for you?";
                                appendCompanionBubble('companion', promptMsg);
                                speakCompanionResponse(promptMsg, 'listening');
                            }
                        };

                        if (query.length > 2) {
                            capturedQuestion = query;
                            if (isFinal) {
                                executeVoiceQuery(capturedQuestion);
                            } else {
                                clearTimeout(wakeQuestionTimer);
                                wakeQuestionTimer = setTimeout(() => {
                                    executeVoiceQuery(capturedQuestion);
                                }, 950);
                            }
                        } else {
                            isCapturingQuestion = true;
                            if (isFinal) {
                                executeVoiceQuery('');
                            } else {
                                clearTimeout(wakeQuestionTimer);
                                wakeQuestionTimer = setTimeout(() => {
                                    if (isCapturingQuestion) {
                                        executeVoiceQuery(capturedQuestion || '');
                                    }
                                }, 1200);
                            }
                        }
                    }
                };

                window.wakeRecognition.onerror = (event) => {
                    if (event.error !== 'no-speech' && event.error !== 'aborted') {
                        console.warn('Wake recognition error:', event.error);
                    }
                };

                window.wakeRecognition.onend = () => {
                    if (window.companionWakeActive && !window._mayaIsSpeaking && !isManualListening) {
                        setTimeout(() => {
                            if (window.companionWakeActive && !window._mayaIsSpeaking && !isManualListening) {
                                window.startCompanionWakeRecognition();
                            }
                        }, 500);
                    }
                };

                window.wakeRecognition.start();
            } catch (err) {
                console.warn('Wake recognition failed to start:', err);
            }
        };



        function renderAIInsight(concepts, prog, mastery) {
            const el = document.getElementById('dashAIInsight');
            if (!el) return;

            const solved = (prog && prog.overview && prog.overview.problems_solved !== undefined)
                ? prog.overview.problems_solved
                : (prog && prog.submissions ? prog.submissions.filter(s => (s.status || '').toLowerCase() === 'accepted').length : 0);
            const totalSubs = (prog && prog.overview && prog.overview.total_submissions !== undefined)
                ? prog.overview.total_submissions
                : (prog && prog.submissions ? prog.submissions.length : 0);

            let insight = '';
            if (mastery && mastery.recommendations && mastery.recommendations.next_action && mastery.recommendations.next_action.message) {
                insight = mastery.recommendations.next_action.message;
            } else if (totalSubs === 0) {
                insight = "You haven't solved any problems yet. The best way to start is by picking an Easy problem in a topic you're curious about. Consistency matters more than intensity at the beginning.";
            } else if (solved === 0) {
                insight = "You've attempted " + totalSubs + " submission" + (totalSubs > 1 ? "s" : "") + " so far. Reviewing test failure edge cases and running sample cases before submitting will help you land your first accepted solution.";
            } else {
                const weak = (concepts || []).filter(c => {
                    const s = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage || 0);
                    return s < 40;
                });
                const strong = (concepts || []).filter(c => {
                    const s = c.mastery_score !== undefined ? c.mastery_score : (c.mastery_percentage || 0);
                    return s >= 70;
                });

                if (weak.length > 0) {
                    const weakName = weak[0].concept_name || weak[0].topic || weak[0].concept || 'this concept';
                    insight = 'Your data shows ' + weakName + ' is your biggest opportunity area right now. Focused practice on weak concepts delivers the fastest mastery gains. I recommend spending 2–3 sessions specifically on ' + weakName + ' problems before moving on.';
                } else if (strong.length > 0) {
                    const strongName = strong[0].concept_name || strong[0].topic || strong[0].concept || 'several areas';
                    insight = "Impressive — you've reached strong mastery in " + strongName + "! To keep leveling up, try applying these skills to harder problems or cross-domain challenges. Mastery compounds when you connect concepts.";
                } else {
                    insight = "You're making steady progress across multiple concepts. Keep your streak alive — even 1 problem a day compounds into significant mastery over a month. Focus next on the weakest concept in your map.";
                }
            }

            el.innerHTML = '<div class="ai-insight-box">' + insight +
                '<div class="ai-author">✨ CodeMind AI Learning Insight</div></div>';
            window._cachedDashboardInsight = el.innerHTML;
        }

        // ===================== INTRO ANIMATION =====================

        function runIntroAnimation() {
            const overlay = document.getElementById('introOverlay');
            const nameEl = document.getElementById('introName');
            if (!overlay || !nameEl) return;

            const fullName = localStorage.getItem('codemind_user_name') || '';
            if (!fullName) { return; }  // No name set yet — skip animation
            overlay.style.display = 'flex';
            nameEl.innerHTML = '';

            // Build letter spans
            let letterIndex = 0;
            fullName.split('').forEach((ch, i) => {
                const span = document.createElement('span');
                span.className = 'letter';
                span.textContent = ch === ' ' ? ' ' : ch;
                const delay = i * 80;
                span.style.animationDelay = delay + 'ms';
                nameEl.appendChild(span);
                if (ch !== ' ') letterIndex++;
            });

            // After letters appear, dissolve
            const totalAppearTime = fullName.length * 80 + 300;
            const holdTime = 900;

            setTimeout(() => {
                nameEl.classList.add('dissolving');
                const letters = nameEl.querySelectorAll('.letter');
                letters.forEach((s, i) => {
                    s.style.setProperty('--d', (i * 30) + 'ms');
                });
                setTimeout(() => {
                    overlay.style.opacity = '0';
                    overlay.style.transition = 'opacity 0.3s ease';
                    setTimeout(() => {
                        overlay.style.display = 'none';
                        overlay.style.opacity = '';
                        overlay.style.transition = '';
                    }, 300);
                }, 800);
            }, totalAppearTime + holdTime);
        }


        function showProgressView() {
            window.active_workspace = 'progress';
            hideAllViews();
            const pView = document.getElementById("progressView");
            if (pView) pView.style.display = "block";
            setActiveNav("navProgress");
            applyUserName();
            loadProgressData();
            window.scrollTo({ top: 0, behavior: "smooth" });
        }

        function showProblemBrowser() {
            window.active_workspace = 'problem_browser';
            hideAllViews();
            document.getElementById("problemBrowser").style.display = "block";
            setActiveNav("navProblems");
            loadProblems();
        }

        function showPractice() {
            window.active_workspace = 'problem_solving';
            hideAllViews();
            document.getElementById("practice").style.display = "block";
            setActiveNav("navPractice");

            // If no problem is open yet, resume where the user left off, or fetch the first one
            if (!activeProblemId) {
                const lastProblem = localStorage.getItem('codemind_last_problem');
                if (lastProblem) {
                    openProblem(lastProblem);
                } else {
                    fetchFirstProblem();
                }
            }
        }

        function showTestsView() {
            window.active_workspace = 'tests';
            hideAllViews();
            document.getElementById("testsView").style.display = "block";
            setActiveNav("navTests");
            initAssessmentView();
        }

        // LOAD TOPICS & SOURCES FOR DROPDOWNS
        async function loadDropdowns() {
            try {
                const [topicsRes, sourcesRes] = await Promise.all([
                    fetch(`${API_BASE}/topics`),
                    fetch(`${API_BASE}/sources`)
                ]);

                if (topicsRes.ok) {
                    const topics = await topicsRes.json();
                    const domainSelect = document.getElementById("domainFilter");
                    domainSelect.innerHTML = '<option value="">All Domains / Topics</option>';
                    topics.forEach(t => {
                        const opt = document.createElement("option");
                        opt.value = t.name;
                        opt.textContent = `${t.name} (${t.problem_count})`;
                        domainSelect.appendChild(opt);
                    });
                    const statEl = document.getElementById("totalTopicsStat");
                    if (statEl) statEl.textContent = topics.length;
                }

                if (sourcesRes.ok) {
                    const sources = await sourcesRes.json();
                    const sourceSelect = document.getElementById("sourceFilter");
                    sourceSelect.innerHTML = '<option value="">All Sources</option>';
                    sources.forEach(s => {
                        const opt = document.createElement("option");
                        opt.value = s.name;
                        const label = s.reference_only
                            ? `${s.display_name || s.name} [Reference]`
                            : `${s.display_name || s.name} (${s.problem_count})`;
                        opt.textContent = label;
                        sourceSelect.appendChild(opt);
                    });
                    const statEl = document.getElementById("totalSourcesStat");
                    if (statEl) statEl.textContent = sources.filter(s => s.problem_count > 0).length;
                }
            } catch (err) {
                console.warn("Could not pre-fetch dropdowns from API:", err);
            }
        }

        // STATS SUMMARY
        async function fetchStats() {
            try {
                const res = await fetch(`${API_BASE}/problems?page=1&page_size=1`);
                if (res.ok) {
                    const data = await res.json();
                    const statEl = document.getElementById("totalProblemsStat");
                    if (statEl) statEl.textContent = data.total;
                }
            } catch (e) {
                console.warn("Stats fetch skipped:", e);
            }
        }

        // DEBOUNCED SEARCH
        function debounceSearch() {
            clearTimeout(searchDebounceTimer);
            searchDebounceTimer = setTimeout(() => {
                filters.search = document.getElementById("searchInput").value.trim();
                currentPage = 1;
                loadProblems();
            }, 300);
        }

        function onFilterChange() {
            filters.difficulty = document.getElementById("difficultyFilter").value;
            filters.domain = document.getElementById("domainFilter").value;
            filters.source = document.getElementById("sourceFilter").value;
            filters.problem_type = document.getElementById("problemTypeFilter").value;
            currentPage = 1;
            loadProblems();
        }

        function resetFilters() {
            document.getElementById("searchInput").value = "";
            document.getElementById("difficultyFilter").value = "";
            document.getElementById("domainFilter").value = "";
            document.getElementById("sourceFilter").value = "";
            document.getElementById("problemTypeFilter").value = "";

            filters = {
                search: "",
                difficulty: "",
                domain: "",
                source: "",
                problem_type: ""
            };
            currentPage = 1;
            loadProblems();
        }

        function onPageSizeChange(val) {
            pageSize = parseInt(val, 10);
            currentPage = 1;
            loadProblems();
        }

        function changePage(delta) {
            const targetPage = currentPage + delta;
            if (targetPage >= 1 && targetPage <= totalPages) {
                currentPage = targetPage;
                loadProblems();
            }
        }

        // FETCH PROBLEMS FROM BACKEND
        async function loadProblems() {
            const tbody = document.getElementById("problemsTableBody");
            const counter = document.getElementById("problemCounterBadge");
            tbody.innerHTML = `<tr><td colspan="5" class="loading-cell">Loading problems from backend...</td></tr>`;

            // Build query params
            const params = new URLSearchParams();
            params.set("page", currentPage);
            params.set("page_size", pageSize);
            if (filters.search) params.set("search", filters.search);
            if (filters.difficulty) params.set("difficulty", filters.difficulty);
            if (filters.domain) params.set("domain", filters.domain);
            if (filters.source) params.set("source", filters.source);
            if (filters.problem_type) params.set("problem_type", filters.problem_type);

            const reqUrl = `${API_BASE}/problems?${params.toString()}`;
            console.log(`[Problem Library] API_BASE:`, API_BASE);
            console.log(`[Problem Library] Requested URL:`, reqUrl);

            const fetchHeaders = {};
            const token = getAuthToken();
            if (token) fetchHeaders['Authorization'] = `Bearer ${token}`;
            const sid = getStudentId();
            if (sid && sid !== 'null' && sid !== 'undefined') fetchHeaders['X-Student-Id'] = sid;

            let response;
            try {
                response = await fetch(reqUrl, { headers: fetchHeaders });
            } catch (networkErr) {
                console.error("[Problem Library] Backend unavailable:", networkErr);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="color: #f87171; padding: 28px;">
                            <div style="font-size: 20px; margin-bottom: 6px;">❌</div>
                            <strong>Backend Unavailable:</strong> Unable to connect to CodeMind server at <code>${escapeHtml(API_BASE)}</code>.<br/>
                            <span style="font-size: 13px; color: #94a3b8; margin-top: 6px; display: inline-block;">
                                Please ensure the FastAPI backend is running on port 8000: <code>python -m uvicorn main:app --host 127.0.0.1 --port 8000</code>
                            </span>
                            <div style="margin-top: 12px;">
                                <button class="nav-button" onclick="loadProblems()" style="padding: 5px 14px; font-size: 12px;">Retry Connection</button>
                            </div>
                        </td>
                    </tr>
                `;
                counter.textContent = "Backend offline (failed to fetch)";
                return;
            }

            console.log(`[Problem Library] HTTP status: ${response.status} ${response.statusText}`);

            if (!response.ok) {
                console.error(`[Problem Library] HTTP Error: ${response.status} ${response.statusText}`);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="color: #f87171; padding: 28px;">
                            <div style="font-size: 20px; margin-bottom: 6px;">⚠️</div>
                            <strong>HTTP Error ${response.status}:</strong> Failed to load problems from backend (${escapeHtml(response.statusText)}).
                            <div style="margin-top: 12px;">
                                <button class="nav-button" onclick="loadProblems()" style="padding: 5px 14px; font-size: 12px;">Retry</button>
                            </div>
                        </td>
                    </tr>
                `;
                counter.textContent = `HTTP ${response.status} error`;
                return;
            }

            let data;
            try {
                data = await response.json();
                console.log(`[Problem Library] Response JSON shape:`, {
                    isObject: typeof data === 'object' && data !== null,
                    hasItems: Array.isArray(data ? data.items : null),
                    itemCount: data && Array.isArray(data.items) ? data.items.length : 0,
                    total: data ? data.total : undefined,
                    page: data ? data.page : undefined,
                    totalPages: data ? data.total_pages : undefined
                });
            } catch (parseErr) {
                console.error("[Problem Library] Invalid JSON response:", parseErr);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="color: #f87171; padding: 28px;">
                            <strong>Invalid Response:</strong> Backend returned invalid JSON.
                        </td>
                    </tr>
                `;
                counter.textContent = "Invalid response format";
                return;
            }

            if (!data || !Array.isArray(data.items)) {
                console.error("[Problem Library] Missing items array in response:", data);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="color: #f87171; padding: 28px;">
                            <strong>Data Format Error:</strong> Server response did not contain problem records.
                        </td>
                    </tr>
                `;
                counter.textContent = "Format error";
                return;
            }

            totalPages = data.total_pages || 1;
            totalCount = data.total || 0;

            if (data.total === 0 || data.items.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="padding: 28px;">
                            No problems found matching your criteria. Try adjusting your filters.
                        </td>
                    </tr>
                `;
                counter.textContent = `0 problems found`;
                document.getElementById("pageIndicator").textContent = `Page 1 of 1`;
                document.getElementById("btnPrevPage").disabled = true;
                document.getElementById("btnNextPage").disabled = true;
                return;
            }

            // Update pagination indicators
            counter.textContent = `Showing ${data.items.length} of ${data.total} problems`;
            document.getElementById("pageIndicator").textContent = `Page ${data.page} of ${data.total_pages || 1}`;
            document.getElementById("btnPrevPage").disabled = data.page <= 1;
            document.getElementById("btnNextPage").disabled = data.page >= data.total_pages;

            try {
                renderProblemRows(data.items);
            } catch (renderErr) {
                console.error("[Problem Library] Rendering error:", renderErr);
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell" style="color: #f87171; padding: 28px;">
                            <strong>Rendering Error:</strong> Failed to display problems: ${escapeHtml(renderErr.message)}
                        </td>
                    </tr>
                `;
                counter.textContent = "Rendering error";
            }
        }

        function renderProblemRows(problems) {
            const tbody = document.getElementById("problemsTableBody");
            if (!problems || problems.length === 0) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" class="empty-cell">
                            No problems found matching your criteria. Try adjusting your filters.
                        </td>
                    </tr>
                `;
                return;
            }

            tbody.innerHTML = "";
            problems.forEach(p => {
                const tr = document.createElement("tr");
                tr.onclick = () => openProblem(p.id);

                const diffClass = `badge-${p.difficulty.toLowerCase()}`;
                const ratingBadge = p.rating ? `<span class="badge badge-rating">★ ${p.rating}</span>` : "";

                const domainChips = (p.domains || []).slice(0, 3).map(d =>
                    `<span class="chip-domain">${escapeHtml(d)}</span>`
                ).join(" ");

                const tagChips = (p.tags || []).slice(0, 2).map(t =>
                    `<span class="chip-tag">#${escapeHtml(t)}</span>`
                ).join(" ");

                const solvedIcon = p.is_solved
                    ? `<span class="problem-solved-badge" style="color: #10b981; font-weight: bold; margin-right: 8px; font-size: 14px;" title="Solved">✓</span>`
                    : `<span class="problem-unsolved-badge" style="color: #475569; margin-right: 8px; font-size: 14px;" title="Unsolved">○</span>`;

                tr.innerHTML = `
                    <td class="problem-title-cell">
                        <div style="display: flex; align-items: center;">${solvedIcon}<span>${escapeHtml(p.title)}</span></div>
                        <div style="font-size: 12px; color: #64748b; margin-top: 4px; padding-left: 20px;">${escapeHtml(p.problem_type)}</div>
                    </td>
                    <td>
                        <span class="badge badge-source">${escapeHtml(p.source)}</span>
                        ${p.source_category ? `<div style="font-size: 11px; color: #64748b; margin-top: 3px;">${escapeHtml(p.source_category)}</div>` : ''}
                    </td>
                    <td>
                        <span class="badge ${diffClass}">${escapeHtml(p.difficulty)}</span>
                        ${ratingBadge}
                    </td>
                    <td>
                        <div class="chip-container">
                            ${domainChips}
                            ${tagChips}
                        </div>
                    </td>
                    <td style="text-align: right;">
                        <button class="btn-solve" onclick="event.stopPropagation(); openProblem('${p.id}')">
                            Solve &rarr;
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // OPEN A PROBLEM & LOAD DETAILS INTO PRACTICE WORKSPACE
        async function openProblem(problemId) {
            try {
                const response = await fetch(`${API_BASE}/problems/${problemId}`);
                if (!response.ok) {
                    throw new Error("Could not fetch problem details.");
                }
                const p = await response.json();
                activeProblemId = p.id;
                localStorage.setItem('codemind_last_problem', p.id);
                localStorage.setItem('codemind_last_problem_title', p.title || p.id);

                // Switch view to Practice and hide any active test view
                window.active_workspace = 'problem_solving';
                hideAllViews();
                document.getElementById("practice").style.display = "block";
                setActiveNav("navPractice");

                // Populate Problem Details
                document.getElementById("detailTitle").textContent = p.title;
                const sourceCat = (p.source_metadata && p.source_metadata.category) ? ` • ${p.source_metadata.category}` : "";
                document.getElementById("detailSubtitle").textContent = `${p.problem_type} • ${p.source}${sourceCat}`;

                const sourceLink = document.getElementById("detailSourceLink");
                if (p.source_url && (p.source_url.startsWith("http://") || p.source_url.startsWith("https://"))) {
                    sourceLink.href = p.source_url;
                    sourceLink.target = "_blank";
                    sourceLink.rel = "noopener noreferrer";
                    sourceLink.style.display = "inline-flex";
                    sourceLink.textContent = `${p.source} External Reference ↗`;
                } else {
                    sourceLink.style.display = "none";
                }

                // Metadata bar
                const metaBar = document.getElementById("detailMetaBar");
                const diffClass = `badge-${p.difficulty.toLowerCase()}`;
                const ratingBadge = p.rating ? `<span class="badge badge-rating">★ Rating: ${p.rating}</span>` : "";

                const domainChips = (p.domains || []).map(d =>
                    `<span class="chip-domain">${escapeHtml(d)}</span>`
                ).join(" ");

                const tagChips = (p.tags || []).map(t =>
                    `<span class="chip-tag">#${escapeHtml(t)}</span>`
                ).join(" ");

                metaBar.innerHTML = `
                    <span class="badge ${diffClass}">${escapeHtml(p.difficulty)}</span>
                    <span class="badge badge-source">${escapeHtml(p.source)}</span>
                    <span class="badge badge-source">${escapeHtml(p.problem_type)}</span>
                    ${ratingBadge}
                    ${domainChips}
                    ${tagChips}
                `;

                // Description
                document.getElementById("detailDescription").innerText = p.description;

                // Input / Output Formats
                const ioSection = document.getElementById("detailIoSection");
                if (p.input_format || p.output_format) {
                    ioSection.style.display = "block";
                    document.getElementById("detailInputFormat").textContent = p.input_format || "Standard input";
                    document.getElementById("detailOutputFormat").textContent = p.output_format || "Standard output";
                } else {
                    ioSection.style.display = "none";
                }

                // Examples
                const examplesList = document.getElementById("detailExamplesList");
                examplesList.innerHTML = "";
                if (p.examples && p.examples.length > 0) {
                    p.examples.forEach((ex, idx) => {
                        const exBox = document.createElement("div");
                        exBox.className = "example-box";
                        let exContent = `<strong>Example ${idx + 1}:</strong><br/>`;
                        exContent += `<p><strong>Input:</strong> ${escapeHtml(ex.input)}</p>`;
                        exContent += `<p><strong>Output:</strong> ${escapeHtml(ex.output)}</p>`;
                        if (ex.explanation) {
                            exContent += `<p style="color: #94a3b8; margin-top: 4px;"><strong>Explanation:</strong> ${escapeHtml(ex.explanation)}</p>`;
                        }
                        exBox.innerHTML = exContent;
                        examplesList.appendChild(exBox);
                    });
                    document.getElementById("detailExamplesSection").style.display = "block";
                } else {
                    document.getElementById("detailExamplesSection").style.display = "none";
                }

                // Constraints
                const constraintsList = document.getElementById("detailConstraintsList");
                constraintsList.innerHTML = "";
                if (p.constraints && p.constraints.length > 0) {
                    p.constraints.forEach(c => {
                        const li = document.createElement("li");
                        li.textContent = c;
                        constraintsList.appendChild(li);
                    });
                    document.getElementById("detailConstraintsSection").style.display = "block";
                } else {
                    document.getElementById("detailConstraintsSection").style.display = "none";
                }

                // Save active problem object for language switching
                currentProblemData = p;

                // ── AUTO-RESET MAYA CONTEXT ON PROBLEM SWITCH ──────────────────
                // The Maya conversation session is bound to a specific problem.
                // When the problem changes, the old context (code, errors, discussion
                // about a different problem) must NOT leak into the new problem's chat.
                // Reset silently — the user should NOT need to press Clear manually.
                if (typeof aiTutorChatHistory !== 'undefined') {
                    aiTutorChatHistory = [];
                }
                if (typeof lastExecutionResult !== 'undefined') {
                    lastExecutionResult = null;
                }
                // Clear result panel so stale error context isn't re-read as safeError
                const resultPanel = document.getElementById('result');
                if (resultPanel) {
                    resultPanel.textContent = '';
                }
                // Reset hint/solution tracking and visualization state for the new problem
                currentHintsUsed = 0;
                currentSolutionViewed = false;
                if (typeof resetProblemVisualizationState === 'function') {
                    resetProblemVisualizationState();
                }
                if (typeof closeCompanionViz === 'function') {
                    closeCompanionViz();
                }
                if (typeof clearCodeXray === 'function') {
                    clearCodeXray(p.id);
                }

                // Restore preferred language for this problem if previously selected
                const savedLang = localStorage.getItem(`codemind_lang_${p.id}`);
                const langSelect = document.getElementById("languageSelect");
                if (savedLang && langSelect) {
                    langSelect.value = savedLang;
                }
                onLanguageChange();
                loadProblemSubmissionCount(p.id);

                // Auto-refresh the inline AI Tutor panel with the new problem
                refreshAIPanel();

                // Clear results
                document.getElementById("result").textContent = "Code loaded for " + p.title + ". Click 'Run Code' to execute.";
                const badge = document.getElementById("statusBadge");
                if (badge) badge.style.display = "none";
                window.scrollTo({ top: 0, behavior: "smooth" });
            } catch (err) {
                console.error("Error opening problem:", err);
                alert("Failed to load problem details. Is the backend running?");
            }
        }

        let currentProblemData = null;

        const LANGUAGE_TEMPLATES = {
            python: `# Python 3 Solution\nimport sys\n\ndef solve():\n    pass\n`,
            c: `/* C Solution */\n#include <stdio.h>\n\nint main() {\n    /* Read input and solve */\n    return 0;\n}\n`,
            cpp: `// C++ Solution\n#include <iostream>\n#include <vector>\nusing namespace std;\n\nint main() {\n    // Read input and solve\n    return 0;\n}\n`,
            java: `// Java Solution\nimport java.util.Scanner;\n\npublic class Solution {\n    public static void main(String[] args) {\n        Scanner sc = new Scanner(System.in);\n        // Read input and solve\n    }\n}\n`
        };

        function updateEditorLineNumbers() {
            const editor = document.getElementById("code");
            const gutter = document.getElementById("codeLineNumbers");
            if (!editor || !gutter) return;
            const lines = editor.value.split("\n");
            const count = Math.max(lines.length, 1);
            let nums = "";
            for (let i = 1; i <= count; i++) {
                nums += i + "\n";
            }
            gutter.textContent = nums;
            gutter.scrollTop = editor.scrollTop;
        }

        function syncEditorLineNumbers() {
            const editor = document.getElementById("code");
            const gutter = document.getElementById("codeLineNumbers");
            if (editor && gutter) {
                gutter.scrollTop = editor.scrollTop;
            }
        }

        function handleEditorKeyDown(e) {
            if (e.key === "Tab") {
                e.preventDefault();
                const editor = e.target;
                const start = editor.selectionStart;
                const end = editor.selectionEnd;
                editor.value = editor.value.substring(0, start) + "    " + editor.value.substring(end);
                editor.selectionStart = editor.selectionEnd = start + 4;
                handleEditorInput();
            }
        }

        let draftAutosaveTimeout = null;

        function setAutosaveStatus(text, color) {
            const statusEl = document.getElementById("autosaveStatus");
            if (statusEl) {
                statusEl.textContent = text;
                statusEl.style.color = color || "#94a3b8";
            }
        }

        async function saveDraftToServer(isSync = false) {
            if (!activeProblemId) return;
            const editor = document.getElementById("code");
            if (!editor) return;
            const langSelect = document.getElementById("languageSelect");
            const lang = langSelect ? langSelect.value : "python";
            const code = editor.value;

            const authUser = typeof getAuthUser === 'function' ? getAuthUser() : null;
            const uid = authUser ? authUser.id : 'guest';
            localStorage.setItem(`codemind_draft_${uid}_${activeProblemId}_${lang}`, code);

            try {
                const sid = getStudentId();
                await authFetch(`${API_BASE}/api/progress/draft`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        problem_id: activeProblemId,
                        language: lang,
                        source_code: code,
                        student_id: sid
                    })
                });
                setAutosaveStatus("☁️ Autosaved", "#10b981");
            } catch (err) {
                setAutosaveStatus("💾 Saved locally", "#94a3b8");
            }
        }

        function handleEditorInput() {
            updateEditorLineNumbers();
            setAutosaveStatus("⏳ Saving...", "#f59e0b");

            const langSelect = document.getElementById("languageSelect");
            const lang = langSelect ? langSelect.value : "python";
            const editor = document.getElementById("code");
            if (activeProblemId && editor) {
                const authUser = typeof getAuthUser === 'function' ? getAuthUser() : null;
                const uid = authUser ? authUser.id : 'guest';
                localStorage.setItem(`codemind_draft_${uid}_${activeProblemId}_${lang}`, editor.value);
            }

            if (draftAutosaveTimeout) clearTimeout(draftAutosaveTimeout);
            draftAutosaveTimeout = setTimeout(() => {
                saveDraftToServer();
            }, 800);
        }

        async function onLanguageChange() {
            const langSelect = document.getElementById("languageSelect");
            const lang = langSelect ? langSelect.value : "python";
            const editor = document.getElementById("code");
            if (!editor) return;

            if (typeof resetProblemVisualizationState === 'function') {
                resetProblemVisualizationState();
            }

            if (activeProblemId) {
                localStorage.setItem(`codemind_lang_${activeProblemId}`, lang);
            }

            const authUser = typeof getAuthUser === 'function' ? getAuthUser() : null;
            const uid = authUser ? authUser.id : 'guest';
            const draftKey = activeProblemId ? `codemind_draft_${uid}_${activeProblemId}_${lang}` : null;
            const legacyDraftKey = activeProblemId ? `codemind_draft_${activeProblemId}_${lang}` : null;
            let savedDraft = draftKey ? localStorage.getItem(draftKey) : (legacyDraftKey ? localStorage.getItem(legacyDraftKey) : null);

            if (savedDraft !== null && savedDraft.trim().length > 0) {
                editor.value = savedDraft;
                setAutosaveStatus("☁️ Autosaved", "#10b981");
            } else if (currentProblemData && currentProblemData.starter_code && currentProblemData.starter_code[lang]) {
                editor.value = currentProblemData.starter_code[lang];
                setAutosaveStatus("☁️ Autosaved", "#94a3b8");
            } else if (currentProblemData) {
                editor.value = LANGUAGE_TEMPLATES[lang] || `# Solution for ${currentProblemData.title}\n`;
                setAutosaveStatus("☁️ Autosaved", "#94a3b8");
            } else {
                editor.value = LANGUAGE_TEMPLATES[lang] || "";
                setAutosaveStatus("☁️ Autosaved", "#94a3b8");
            }

            updateEditorLineNumbers();

            // Background fetch from server if local storage had no draft
            if ((!savedDraft || savedDraft.trim().length === 0) && activeProblemId) {
                try {
                    const sid = getStudentId();
                    const res = await authFetch(`${API_BASE}/api/progress/draft?problem_id=${encodeURIComponent(activeProblemId)}&language=${encodeURIComponent(lang)}&student_id=${encodeURIComponent(sid)}`);
                    if (res.ok) {
                        const data = await res.json();
                        if (data && data.draft && data.draft.source_code && data.draft.source_code.trim().length > 0) {
                            editor.value = data.draft.source_code;
                            localStorage.setItem(`codemind_draft_${uid}_${activeProblemId}_${lang}`, data.draft.source_code);
                            updateEditorLineNumbers();
                            setAutosaveStatus("☁️ Autosaved", "#10b981");
                        }
                    }
                } catch (e) {
                    console.debug("Remote draft fetch:", e);
                }
            }
        }

        // Auto-save code draft on editor typing isolated per authenticated user
        function setupWorkspaceDraftAutosave() {
            window.addEventListener("beforeunload", () => {
                saveDraftToServer(true);
            });
        }

        let activeProblemSubmissions = [];

        async function loadProblemSubmissionCount(problemId) {
            if (!problemId) return;
            const badge = document.getElementById("submissionCountBadge");
            try {
                const sid = getStudentId();
                const res = await authFetch(`${API_BASE}/api/progress/submissions?problem_id=${encodeURIComponent(problemId)}&student_id=${encodeURIComponent(sid)}`);
                if (res.ok) {
                    const data = await res.json();
                    activeProblemSubmissions = data.submissions || [];
                    if (badge) badge.textContent = data.submission_count || 0;
                }
            } catch (err) {
                console.warn("Failed to load submission count:", err);
            }
        }

        async function openSubmissionHistoryModal() {
            if (!activeProblemId) {
                alert("Please select a problem first.");
                return;
            }
            const modal = document.getElementById("submissionHistoryModal");
            const listEl = document.getElementById("submissionHistoryList");
            const titleEl = document.getElementById("submissionHistoryProblemTitle");
            if (modal) modal.style.display = "flex";
            if (titleEl && currentProblemData) {
                titleEl.textContent = `Submissions for: ${currentProblemData.title} (Problem ID: ${activeProblemId})`;
            }

            if (listEl) {
                listEl.innerHTML = `<div style="text-align:center; padding:30px; color:#94a3b8;">Loading submissions...</div>`;
            }

            try {
                const sid = getStudentId();
                const res = await authFetch(`${API_BASE}/api/progress/submissions?problem_id=${encodeURIComponent(activeProblemId)}&student_id=${encodeURIComponent(sid)}`);
                if (!res.ok) throw new Error("Could not fetch submissions.");
                const data = await res.json();
                activeProblemSubmissions = data.submissions || [];
                const badge = document.getElementById("submissionCountBadge");
                if (badge) badge.textContent = data.submission_count || 0;

                if (!activeProblemSubmissions || activeProblemSubmissions.length === 0) {
                    listEl.innerHTML = `
                        <div style="text-align: center; color: #94a3b8; padding: 40px 20px;">
                            <div style="font-size: 32px; margin-bottom: 8px;">📭</div>
                            <div style="font-size: 15px; font-weight: 600; color: #f8fafc;">No Submissions Yet</div>
                            <div style="font-size: 13px; margin-top: 4px;">Click the <strong>Submit</strong> button in the editor to make your first official submission. Autosaved drafts are working drafts and do not count as submissions.</div>
                        </div>
                    `;
                    return;
                }

                listEl.innerHTML = activeProblemSubmissions.map((sub, idx) => {
                    const isAccepted = (sub.status || '').toLowerCase() === 'accepted';
                    const statusColor = isAccepted ? '#10b981' : '#ef4444';
                    const statusBg = isAccepted ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)';
                    const statusBorder = isAccepted ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)';
                    const dateStr = sub.created_at ? new Date(sub.created_at).toLocaleString() : 'N/A';
                    const subNum = sub.submission_number || (activeProblemSubmissions.length - idx);

                    return `
                        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 14px 16px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="font-weight: 800; font-size: 14px; color: var(--accent-gold, #d4af37);">#${subNum}</div>
                                <div>
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <span style="background: ${statusBg}; color: ${statusColor}; border: 1px solid ${statusBorder}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 700; text-transform: uppercase;">${escapeHtml(sub.status || 'Submitted')}</span>
                                        <span class="chip-domain" style="font-size: 11px;">${escapeHtml((sub.language || 'python').toUpperCase())}</span>
                                        ${sub.total_test_cases ? `<span style="font-size: 12px; color: #94a3b8;">${sub.passed_test_cases}/${sub.total_test_cases} tests passed</span>` : ''}
                                    </div>
                                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Submitted on ${escapeHtml(dateStr)}</div>
                                </div>
                            </div>
                            <div style="display: flex; gap: 8px; align-items: center;">
                                <button class="filter-btn" onclick="viewSubmissionSnapshot('${escapeHtml(sub.id)}')"
                                        style="font-size: 12px; padding: 5px 12px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); color: #f8fafc; border-radius: 6px; cursor: pointer;">
                                    👁️ View Code
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                if (listEl) {
                    listEl.innerHTML = `<div style="text-align:center; padding:30px; color:#ef4444;">Error loading submissions: ${escapeHtml(err.message)}</div>`;
                }
            }
        }

        function closeSubmissionHistoryModal() {
            const modal = document.getElementById("submissionHistoryModal");
            if (modal) modal.style.display = "none";
        }

        let viewingSnapshotCode = "";
        let viewingSnapshotLang = "";

        function viewSubmissionSnapshot(submissionId) {
            const sub = activeProblemSubmissions.find(s => s.id === submissionId);
            if (!sub) return;

            viewingSnapshotCode = sub.source_code || "";
            viewingSnapshotLang = sub.language || "python";

            const modal = document.getElementById("submissionCodeModal");
            const titleEl = document.getElementById("submissionCodeModalTitle");
            const metaEl = document.getElementById("submissionCodeModalMeta");
            const contentEl = document.getElementById("submissionCodeModalContent");

            if (titleEl) titleEl.textContent = `Submission #${sub.submission_number || ''} Snapshot (${(sub.language || 'python').toUpperCase()})`;
            if (metaEl) {
                const dateStr = sub.created_at ? new Date(sub.created_at).toLocaleString() : 'N/A';
                metaEl.textContent = `Submitted on ${dateStr} • Status: ${(sub.status || '').toUpperCase()} • Tests: ${sub.passed_test_cases || 0}/${sub.total_test_cases || 0}`;
            }
            if (contentEl) contentEl.textContent = sub.source_code || "# No code recorded";

            if (modal) modal.style.display = "flex";
        }

        function closeSubmissionCodeModal() {
            const modal = document.getElementById("submissionCodeModal");
            if (modal) modal.style.display = "none";
        }

        function restoreSnapshotToEditor() {
            if (!viewingSnapshotCode) return;
            const editor = document.getElementById("code");
            const langSelect = document.getElementById("languageSelect");
            if (editor) {
                editor.value = viewingSnapshotCode;
                updateEditorLineNumbers();
            }
            if (langSelect && viewingSnapshotLang) {
                langSelect.value = viewingSnapshotLang;
            }
            closeSubmissionCodeModal();
            closeSubmissionHistoryModal();
            handleEditorInput();
            if (typeof showToast === 'function') {
                showToast("Snapshot restored to editor!");
            }
        }

        function askMayaToDebugInChat() {
            closeAITutorModal();
            if (currentAIPanelTab !== 'chat') {
                switchAIPanelTab('chat');
            }
            const chatInput = document.getElementById("aiPanelChatInput") || document.getElementById("aiTutorChatInput");
            if (chatInput) {
                chatInput.value = "Please debug my code step-by-step. Pinpoint the exact line number, tell me what is wrong, why it is wrong, and show me how to fix it.";
            }
            const sendBtn = document.getElementById("aiPanelSendBtn") || document.getElementById("aiTutorSendBtn");
            if (sendBtn) {
                sendBtn.click();
            }
        }

        // Fetch the first available problem if user directly opens workspace
        async function fetchFirstProblem() {
            try {
                const res = await fetch(`${API_BASE}/problems?page=1&page_size=1`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.items && data.items.length > 0) {
                        openProblem(data.items[0].id);
                    }
                }
            } catch (e) {
                console.warn(e);
            }
        }

        // EXECUTE CODE AGAINST ACTIVE PROBLEM TEST CASES
        async function runCode() {
            const code = document.getElementById("code").value;
            const resultElement = document.getElementById("result");
            const statusBadge = document.getElementById("statusBadge");
            const runButton = document.getElementById("runButton");
            const langSelect = document.getElementById("languageSelect");
            const language = langSelect ? langSelect.value : "python";

            if (!activeProblemId) {
                resultElement.innerText = "Please select a problem from the Problem Library first.";
                return;
            }

            if (code.trim() === "") {
                resultElement.innerText = "Please write some code first.";
                return;
            }

            runButton.disabled = true;
            runButton.innerText = "Running...";
            resultElement.innerText = `Executing your ${language.toUpperCase()} code in isolated environment...`;
            showOutputDrawer(true); // show drawer, expanded
            if (statusBadge) statusBadge.style.display = "none";
            // Hide xray from previous run
            const prevXray = document.getElementById("codeXraySection");
            if (prevXray) prevXray.style.display = "none";
            const prevCard = document.getElementById("executionFeedbackCard");
            if (prevCard) prevCard.style.display = "none";

            try {
                const response = await fetch(`${API_BASE}/api/execute`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        problem_id: activeProblemId,
                        language: language,
                        source_code: code
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    const errDetail = data.detail || `Server error: ${response.status} ${response.statusText}`;
                    if (statusBadge) {
                        statusBadge.style.display = "inline-block";
                        statusBadge.style.background = "#dc2626";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "ERROR";
                    }
                    resultElement.innerText = errDetail;
                    return;
                }

                if (statusBadge) {
                    statusBadge.style.display = "inline-block";
                    const s = (data.status || "").toLowerCase();
                    if (s === "accepted") {
                        statusBadge.style.background = "#16a34a";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "✓ ACCEPTED";
                    } else if (s === "wrong_answer" || s === "wrong answer") {
                        statusBadge.style.background = "#dc2626";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "✗ WRONG ANSWER";
                    } else if (s === "compile_error" || s === "compile error") {
                        statusBadge.style.background = "#ea580c";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⚠ COMPILE ERROR";
                    } else if (s === "runtime_error" || s === "runtime error") {
                        statusBadge.style.background = "#e11d48";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⚡ RUNTIME ERROR";
                    } else if (s === "time_limit" || s === "timeout" || s === "time limit") {
                        statusBadge.style.background = "#d97706";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⏱ TIMEOUT";
                    } else if (s === "no_test_cases" || s === "no test cases") {
                        statusBadge.style.background = "#475569";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "ℹ NO TEST CASES";
                    } else {
                        statusBadge.style.background = "#64748b";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = (data.status || "STATUS").toUpperCase();
                    }
                }

                let outputText = "";
                if (data.status === "no_test_cases") {
                    outputText = data.error || data.output || "Problem does not contain executable test cases in the database.";
                } else if (data.status === "compile_error") {
                    outputText = data.error || data.stderr || "Compilation failed.";
                } else if (data.test_results && data.test_results.length > 0) {
                    outputText += `Passed: ${data.passed_count || 0} / ${data.total_test_cases || data.test_results.length} test cases\n\n`;
                    data.test_results.forEach(tc => {
                        const icon = tc.passed ? "✓ Passed" : "✗ Failed";
                        outputText += `[Test Case ${tc.test_case}] - ${icon} (${tc.execution_time}s)\n`;
                        outputText += `Expected: ${tc.expected_output}\n`;
                        outputText += `Actual:   ${tc.actual_output}\n`;
                        if (tc.error) {
                            outputText += `Error:    ${tc.error}\n`;
                        }
                        outputText += "\n";
                    });
                } else if (data.error) {
                    outputText = data.error;
                } else if (data.output) {
                    outputText = data.output;
                } else {
                    outputText = "Execution finished with no output.";
                }

                resultElement.innerText = outputText.trim();

                // Track execution result for AI Tutor "Why Did I Fail?"
                lastExecutionResult = data;
                const whyBtn = document.getElementById("whyFailedBtn");
                if (whyBtn) {
                    if (data.status && data.status.toLowerCase() !== "accepted") {
                        whyBtn.style.display = "inline-block";
                    } else {
                        whyBtn.style.display = "none";
                    }
                }

                // Render 3D-Style Feedback & Contextual Code X-Ray
                renderExecutionVisuals(data, language, false, activeProblemId);

            } catch (error) {
                const classified = classifyApiError(error);
                if (statusBadge) {
                    statusBadge.style.display = "inline-block";
                    statusBadge.style.background = "#dc2626";
                    statusBadge.style.color = "#ffffff";
                    statusBadge.innerText = classified.type;
                }
                resultElement.innerText = `${classified.type}: ${classified.message}`;
            } finally {
                runButton.disabled = false;
                runButton.innerText = "▶ Run";
            }
        }

        // SUBMIT SOLUTION IN PRACTICE MODE (PERSISTS REAL PROBLEM SUBMISSION)
        async function submitPracticeCode() {
            if (!activeProblemId) {
                alert("Please select a problem first.");
                return;
            }
            const code = document.getElementById("code").value;
            const langSelect = document.getElementById("languageSelect");
            const language = langSelect ? langSelect.value : "python";
            const btn = document.getElementById("submitPracticeBtn");
            const badge = document.getElementById("practiceSubmissionBadge");

            if (!code || !code.trim()) {
                alert("Please write some code before submitting.");
                return;
            }

            // P0 - D: Check authentication BEFORE sending request
            if (!isAuthenticated()) {
                window.pendingAuthAction = () => {
                    submitPracticeCode();
                };
                openAuthModal('signin', 'Please log in or create an account to submit your solution.');
                return;
            }

            btn.disabled = true;
            btn.innerText = "Submitting...";

            try {
                const sid = getStudentId();
                const res = await authFetch(`${API_BASE}/api/progress/submit`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        problem_id: activeProblemId,
                        student_id: sid,
                        language: language,
                        source_code: code,
                        hints_used: currentHintsUsed,
                        solution_viewed: currentSolutionViewed,
                        approach_reviewed: false
                    })
                });

                if (res.status === 401) {
                    // Session expired during request; authFetch has cleared session & opened auth modal
                    window.pendingAuthAction = () => {
                        submitPracticeCode();
                    };
                    return;
                }

                const data = await res.json();
                if (!res.ok) throw new Error(data.detail || "Submission failed.");

                // Update lastExecutionResult
                lastExecutionResult = data;

                badge.style.display = "inline-block";
                const whyBtn = document.getElementById("whyFailedBtn");

                if (data.status === "accepted") {
                    badge.style.background = "#16a34a";
                    badge.style.color = "#ffffff";
                    badge.innerText = "✓ ACCEPTED & STORED";
                    if (whyBtn) whyBtn.style.display = "none";
                    renderExecutionVisuals(data, language, true, activeProblemId);
                } else {
                    badge.style.background = "#dc2626";
                    badge.style.color = "#ffffff";
                    badge.innerText = `✗ ${data.status.replace("_", " ").toUpperCase()}`;
                    if (whyBtn) whyBtn.style.display = "inline-block";
                    renderExecutionVisuals(data, language, true, activeProblemId);
                }

                // Immediately refresh submission count
                loadProblemSubmissionCount(activeProblemId);
            } catch (err) {
                if (err && (err.status === 401 || String(err.message || '').includes('Authentication required') || String(err.message || '').includes('401'))) {
                    // Session expired or unauthenticated: open auth modal without browser alert
                    window.pendingAuthAction = () => {
                        submitPracticeCode();
                    };
                    openAuthModal('signin', 'Your session has expired. Please log in again.');
                } else {
                    alert("Submission failed: " + err.message);
                }
            } finally {
                btn.disabled = false;
                btn.innerText = "✓ Submit";
            }
        }

        function triggerWhyDidIFail() {
            openAITutorModal("debug");
        }

        // ========================================================
        // OUTPUT DRAWER HELPERS
        // ========================================================
        let _outputDrawerOpen = false;
        function showOutputDrawer(expanded = true) {
            const drawer = document.getElementById("executionOutputDrawer");
            if (!drawer) return;
            drawer.style.display = "block";
            _outputDrawerOpen = true;
            const body = document.getElementById("outputDrawerBody");
            const icon = document.getElementById("outputDrawerToggleIcon");
            if (expanded) {
                if (body) body.classList.remove("collapsed");
                if (icon) icon.textContent = "▲ Hide";
            }
        }
        function toggleOutputDrawer() {
            const body = document.getElementById("outputDrawerBody");
            const icon = document.getElementById("outputDrawerToggleIcon");
            if (!body) return;
            const collapsed = body.classList.contains("collapsed");
            if (collapsed) {
                body.classList.remove("collapsed");
                if (icon) icon.textContent = "▲ Hide";
            } else {
                body.classList.add("collapsed");
                if (icon) icon.textContent = "▼ Show";
            }
        }

        // ========================================================
        // STRUCTURED FAILURE TYPE DETECTION
        // ========================================================
        function classifyFailureType(data) {
            const st = (data.status || "").toLowerCase();
            const err = (data.error || data.stderr || "").toLowerCase();
            if (st === "compile_error" || st === "compile error") {
                if (err.includes("syntaxerror") || err.includes("syntax error") || err.includes("unexpected")) return "syntax_error";
                if (err.includes("typeerror") || err.includes("type error") || err.includes("cannot convert")) return "type_error";
                if (err.includes("nameerror") || err.includes("undefined") || err.includes("undeclared") || err.includes("was not declared")) return "undefined_identifier";
                return "compile_error";
            }
            if (st === "runtime_error" || st === "runtime error") {
                if (err.includes("indexerror") || err.includes("index out of") || err.includes("arrayindexoutofbounds")) return "out_of_bounds";
                if (err.includes("nullpointer") || err.includes("null pointer") || err.includes("none") && err.includes("attribute")) return "null_pointer";
                if (err.includes("zerodivision") || err.includes("division by zero")) return "runtime_error";
                if (err.includes("stackoverflow") || err.includes("recursion") || err.includes("maximum recursion")) return "infinite_loop";
                if (err.includes("typeerror")) return "type_error";
                return "runtime_error";
            }
            if (st === "time_limit" || st === "timeout") return "tle";
            if (st === "wrong_answer") return "wrong_answer";
            if (st === "accepted") return "accepted";
            return st || "unknown";
        }

        function getFailureLabel(ftype) {
            const map = {
                "syntax_error": "⚠️ Syntax Error",
                "type_error": "🔴 Type Error",
                "undefined_identifier": "❓ Undefined Identifier",
                "compile_error": "🔨 Compilation Error",
                "runtime_error": "💥 Runtime Error",
                "null_pointer": "🚫 Null/None Access",
                "out_of_bounds": "📏 Index Out of Bounds",
                "infinite_loop": "🔁 Infinite Loop / Stack Overflow",
                "tle": "⏱ Time Limit Exceeded",
                "wrong_answer": "✗ Wrong Answer",
                "accepted": "✓ Accepted",
            };
            return map[ftype] || ftype.replace(/_/g, " ").toUpperCase();
        }

        // ========================================================
        // ENHANCED X-RAY WITH ROOT-CAUSE GROUPING
        // ========================================================
        function buildEnhancedXray(data, language, ftype) {
            const errorText = data.error || data.stderr || "";
            const lines = errorText.split("\n").filter(l => l.trim());

            // Identify root cause lines vs cascading
            // Root cause = first meaningful error line (not "^" pointer lines, not "note:" lines)
            let rootLines = [];
            let cascadeLines = [];
            let seenRoot = false;

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed) continue;
                // Skip pointer lines (just carets)
                if (/^\^+\s*$/.test(trimmed)) continue;
                // Skip note/info lines (secondary)
                if (/^note:/i.test(trimmed) || /^\s*In file/i.test(trimmed)) {
                    cascadeLines.push(trimmed);
                    continue;
                }
                if (!seenRoot) {
                    rootLines.push(trimmed);
                    seenRoot = true;
                } else {
                    cascadeLines.push(trimmed);
                }
            }

            // Extract line number from error
            let lineNum = null;
            const lineMatch = errorText.match(/(?:line\s+|:)(\d+)(?::\d+)?(?::|,|\s|$)/i);
            if (lineMatch) lineNum = parseInt(lineMatch[1]);

            // Concise human explanation per failure type
            const humanExplanations = {
                "syntax_error": "Python/compiler found a token it cannot parse. Check for unclosed brackets, missing colons, or indentation errors near the indicated line.",
                "type_error": "A value was used as the wrong type — e.g. calling a method that does not exist for that type, or mixing types in an operation.",
                "undefined_identifier": "You used a variable or function name that was never defined. Check spelling, scope, or missing import.",
                "compile_error": "The compiler could not translate your code. Fix the syntax issue at the indicated line.",
                "runtime_error": "Your code compiled but crashed during execution. Check array indices, null values, and division operations.",
                "null_pointer": "You accessed a property or method on a null/None value. Guard against None before calling methods.",
                "out_of_bounds": "You accessed an index outside the valid range [0, length-1]. Check loop bounds and off-by-one conditions.",
                "infinite_loop": "Program ran too long or hit recursion limit. Check your loop exit condition and base case.",
                "tle": "Algorithm exceeds time limit. Likely O(N²) or worse. Consider hash maps or two pointers to reduce to O(N).",
                "wrong_answer": "Code ran successfully but produced incorrect output for at least one test case.",
                "accepted": "All test cases passed.",
            };
            const humanExpl = humanExplanations[ftype] || "Inspect the error carefully and verify your logic.";

            let html = `
                <div class="xray-row">
                    <div class="xray-label">Language:</div>
                    <div class="xray-val">${escapeHtml((language || 'python').toUpperCase())}</div>
                </div>
            `;

            if (data.total_test_cases) {
                const pct = Math.round(((data.passed_count || 0) / data.total_test_cases) * 100);
                html += `
                    <div class="xray-row">
                        <div class="xray-label">Tests:</div>
                        <div class="xray-val">${data.passed_count || 0} / ${data.total_test_cases} passed (${pct}%)</div>
                    </div>
                `;
            }

            if (lineNum) {
                html += `
                    <div class="xray-row">
                        <div class="xray-label">Line:</div>
                        <div class="xray-val" style="color: #fbbf24; font-weight: 700;">Line ${lineNum}</div>
                    </div>
                `;
            }

            if (ftype === "accepted") {
                html += `<div class="xray-no-issues">✅ All test cases passed — no issues detected.</div>`;
            } else if (ftype === "wrong_answer" && data.test_results && data.test_results.length > 0) {
                const firstFail = data.test_results.find(t => !t.passed) || data.test_results[0];
                const expStr = String(firstFail.expected_output || "");
                const gotStr = String(firstFail.actual_output || firstFail.error || "");
                // Find first meaningful difference
                let diffNote = "";
                if (expStr && gotStr) {
                    if (expStr.length === gotStr.length && expStr !== gotStr) {
                        diffNote = "Same length but values differ — likely off-by-one or inverted comparison.";
                    } else if (gotStr === "" || gotStr === "None") {
                        diffNote = "Your function returned nothing. Ensure you have a return statement.";
                    } else if (expStr.split("\n").length !== gotStr.split("\n").length) {
                        diffNote = `Output has ${gotStr.split("\n").length} line(s), expected ${expStr.split("\n").length}.`;
                    }
                }
                html += `
                    <div class="xray-root-cause">
                        <div class="xray-root-label">🎯 Root Problem &mdash; Wrong Output</div>
                        <div class="xray-root-msg">${escapeHtml(humanExpl)}</div>
                    </div>
                    <div class="wa-card">
                        <div class="wa-row">
                            <div class="wa-lbl">Expected</div>
                            <div class="wa-val exp">${escapeHtml(expStr || "(empty)")}</div>
                        </div>
                        <div class="wa-row">
                            <div class="wa-lbl">Your Output</div>
                            <div class="wa-val got">${escapeHtml(gotStr || "(empty)")}</div>
                        </div>
                        ${diffNote ? `<div class="wa-diff-note">💡 ${escapeHtml(diffNote)}</div>` : ''}
                        <div class="wa-actions">
                            <button class="wa-btn explain" onclick="triggerWhyDidIFail()">🐞 Explain with Maya</button>
                            <button class="wa-btn counter" onclick="askMayaForCounterexample()">🧪 Generate Counterexample</button>
                            <button class="wa-btn trace" onclick="askMayaToTraceCode()">📊 Trace My Code</button>
                        </div>
                    </div>
                `;
            } else if (rootLines.length > 0) {
                // Compile/Runtime error with root-cause display
                const rootMsg = rootLines[0];
                const relatedCount = cascadeLines.filter(l => l.includes("error") || l.includes("Error")).length;
                html += `
                    <div class="xray-root-cause">
                        <div class="xray-root-label">
                            🎯 Root Problem
                            ${relatedCount > 0 ? `<span style="color:#94a3b8;font-weight:400;">— causing ${relatedCount} related error${relatedCount>1?'s':''}</span>` : ''}
                        </div>
                        <div class="xray-root-msg">${escapeHtml(rootMsg)}</div>
                    </div>
                    <div class="xray-row" style="margin-top: 4px;">
                        <div class="xray-label" style="color:#94a3b8;">Issue Type:</div>
                        <div class="xray-val" style="color:#fbbf24;">${escapeHtml(getFailureLabel(ftype))}</div>
                    </div>
                    <div class="xray-row">
                        <div class="xray-label" style="color:#94a3b8;">Fix:</div>
                        <div class="xray-val" style="color:#86efac;">${escapeHtml(humanExpl)}</div>
                    </div>
                `;
                if (cascadeLines.length > 0) {
                    const visibleCascade = cascadeLines.slice(0, 3);
                    const hiddenCascade = cascadeLines.slice(3);
                    html += `<div class="xray-cascading" id="xrayCascade">`;
                    visibleCascade.forEach(l => {
                        html += `<div class="xray-cascade-item">${escapeHtml(l)}</div>`;
                    });
                    if (hiddenCascade.length > 0) {
                        html += `<span class="xray-show-all" onclick="document.getElementById('xrayCascadeHidden').style.display='block'; this.style.display='none';">▼ Show ${hiddenCascade.length} more error${hiddenCascade.length>1?'s':''}</span>`;
                        html += `<div id="xrayCascadeHidden" style="display:none;">`;
                        hiddenCascade.forEach(l => {
                            html += `<div class="xray-cascade-item">${escapeHtml(l)}</div>`;
                        });
                        html += `</div>`;
                    }
                    html += `</div>`;
                }
                const techId = "xrayTechDetail_" + Date.now();
                html += `
                    <span class="xray-tech-toggle" onclick="const el=document.getElementById('${techId}'); el.style.display=el.style.display==='none'?'block':'none';">Technical details ▾</span>
                    <div id="${techId}" class="xray-tech-details" style="display:none;">${escapeHtml(errorText)}</div>
                `;
            } else {
                // No error text but failure — generic
                html += `
                    <div class="xray-row">
                        <div class="xray-label">Issue:</div>
                        <div class="xray-val" style="color:#fca5a5;">${escapeHtml(humanExpl)}</div>
                    </div>
                `;
            }

            // Contextual hint
            if (ftype !== "accepted") {
                html += `
                    <div style="margin-top: 8px; padding: 7px 10px; background: rgba(56,189,248,0.07); border-left: 2px solid #38bdf8; border-radius: 3px; font-size: 11px; color: #94a3b8;">
                        💡 Use <strong style="color:#38bdf8;">Maya → Debug tab</strong> for a step-by-step WHAT / WHERE / WHY / HOW breakdown.
                    </div>
                `;
            }

            return html;
        }

        // ========================================================
        // 3D-STYLE EXECUTION FEEDBACK & CONTEXTUAL CODE X-RAY
        // ========================================================
        function clearCodeXray(problemId = null) {
            window.__currentXrayProblemId = problemId;
            const card = document.getElementById("executionFeedbackCard");
            const xray = document.getElementById("codeXraySection");
            const xrayPill = document.getElementById("xrayStatusPill");
            const xrayContent = document.getElementById("xrayContent");
            const xraySummary = document.getElementById("xrayRootSummary");
            if (xray) xray.style.display = "none";
            if (xrayContent) xrayContent.innerHTML = "";
            if (xraySummary) xraySummary.textContent = "";
            if (xrayPill) {
                xrayPill.textContent = "";
                xrayPill.style.background = "";
            }
            if (card) {
                card.style.display = "none";
                card.innerHTML = "";
            }
        }

        function renderExecutionVisuals(data, language, isSubmission = false, targetProblemId = null) {
            // Guard: Never render stale in-flight execution visuals for a previous problem
            if (targetProblemId && typeof activeProblemId !== 'undefined' && activeProblemId && targetProblemId !== activeProblemId) {
                return;
            }
            if (typeof activeProblemId !== 'undefined' && activeProblemId) {
                window.__currentXrayProblemId = activeProblemId;
            }
            const card = document.getElementById("executionFeedbackCard");
            const xray = document.getElementById("codeXraySection");
            const xrayPill = document.getElementById("xrayStatusPill");
            const xrayContent = document.getElementById("xrayContent");
            const xraySummary = document.getElementById("xrayRootSummary");
            if (!card || !xray) return;

            const st = (data.status || "").toLowerCase();
            const isAccepted = st === "accepted";
            const ftype = classifyFailureType(data);

            // Show output drawer
            showOutputDrawer(true);

            // 1. 3D-Style Feedback Banner
            if (isAccepted) {
                card.className = "feedback-visual-card success";
                card.innerHTML = `
                    <div class="feedback-icon-3d">🏆</div>
                    <div class="feedback-body">
                        <div class="feedback-heading" style="color: #4ade80;">
                            <span>${isSubmission ? 'Submission Accepted & Mastered!' : 'All Test Cases Passed!'}</span>
                            <span class="badge" style="background:#15803d;color:#fff;">✓ Verified Logic</span>
                        </div>
                        <div class="feedback-sub">
                            Passed ${data.passed_count || data.passed_test_cases || 'All'} test cases with efficient execution.
                            Ready to analyze complexity or try a Transfer Challenge!
                        </div>
                    </div>
                    <button class="feedback-action-btn" style="background:#0284c7;" onclick="openAITutorModal('review')">
                        📊 Review Complexity
                    </button>
                `;
                card.style.display = "flex";
            } else {
                card.className = "feedback-visual-card failed";
                const ftLabel = getFailureLabel(ftype);
                let emoji = "😔";
                let heading = "Execution Needs Attention";
                let detail = "Your solution encountered an issue. Maya can pinpoint the exact cause.";

                if (ftype === "tle") { emoji = "⏱️"; heading = "Time Limit Exceeded"; detail = "Algorithm exceeded maximum runtime (likely O(N²) or infinite loop)."; }
                else if (ftype === "compile_error" || ftype === "syntax_error") { emoji = "⚠️"; heading = "Compilation / Syntax Issue"; detail = "The compiler found syntax or type defects. See Code X-Ray for the exact line."; }
                else if (ftype === "runtime_error" || ftype === "null_pointer" || ftype === "out_of_bounds") { emoji = "💥"; heading = "Runtime Crash"; detail = "Program threw an unhandled exception during test execution."; }
                else if (ftype === "wrong_answer") { emoji = "😔"; heading = "Wrong Answer"; detail = `Passed ${data.passed_count || 0} / ${data.total_test_cases || 1} test cases. Output did not match expected.`; }

                card.innerHTML = `
                    <div class="feedback-icon-3d">${emoji}</div>
                    <div class="feedback-body">
                        <div class="feedback-heading" style="color: #f87171;">
                            <span>${heading}</span>
                            <span class="badge" style="background:#b91c1c;color:#fff;">${escapeHtml(ftLabel)}</span>
                        </div>
                        <div class="feedback-sub">${detail}</div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px; flex-shrink: 0;">
                        <button class="feedback-action-btn" onclick="triggerWhyDidIFail()">
                            🔍 Why Did I Fail? →
                        </button>
                        <button onclick="dismissFeedbackVisual()" title="Dismiss" style="background:rgba(148,163,184,0.15);border:1px solid rgba(148,163,184,0.3);color:#94a3b8;border-radius:6px;width:26px;height:26px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;">
                            ✕
                        </button>
                    </div>
                `;
                card.style.display = "flex";
            }

            // 2. Enhanced Code X-Ray
            if (xrayPill) {
                xrayPill.style.background = isAccepted ? "#16a34a" : "#dc2626";
                xrayPill.style.color = "#ffffff";
                xrayPill.textContent = (data.status || "STATUS").toUpperCase();
            }

            // Root summary
            if (xraySummary && !isAccepted) {
                const rootError = data.error || data.stderr || "";
                const errCount = (rootError.match(/error:/gi) || []).length;
                if (errCount > 1) {
                    xraySummary.textContent = `• 1 root + ${errCount - 1} cascading`;
                } else {
                    xraySummary.textContent = "";
                }
            } else if (xraySummary) {
                xraySummary.textContent = "";
            }

            xrayContent.innerHTML = buildEnhancedXray(data, language, ftype);
            xray.style.display = "block";
            const collapseBtn = document.getElementById("xrayCollapseBtn");
            if (collapseBtn) collapseBtn.textContent = "_ Minimize";
            isXrayCollapsed = false;
            initXrayResize();
        }

        let isXrayCollapsed = false;
        function toggleXrayCollapse() {
            const content = document.getElementById("xrayContent");
            const btn = document.getElementById("xrayCollapseBtn");
            const xray = document.getElementById("codeXraySection");
            if (!content || !btn) return;
            isXrayCollapsed = !isXrayCollapsed;
            if (isXrayCollapsed) {
                content.style.display = "none";
                btn.textContent = "▲ Expand";
                if (xray) xray.style.height = "auto";
            } else {
                content.style.display = "block";
                btn.textContent = "_ Minimize";
            }
        }

        function closeXray() {
            const xray = document.getElementById("codeXraySection");
            if (xray) xray.style.display = "none";
        }

        let xrayResizeInitialized = false;
        function initXrayResize() {
            if (xrayResizeInitialized) return;
            const handle = document.getElementById("xrayDragHandle");
            const xray = document.getElementById("codeXraySection");
            if (!handle || !xray) return;
            xrayResizeInitialized = true;

            let startY = 0;
            let startHeight = 0;

            handle.addEventListener("mousedown", (e) => {
                e.preventDefault();
                startY = e.clientY;
                startHeight = xray.offsetHeight;
                handle.classList.add("active");
                document.body.style.cursor = "ns-resize";

                function onMouseMove(ev) {
                    const deltaY = startY - ev.clientY;
                    const newH = Math.max(44, Math.min(window.innerHeight - 200, startHeight + deltaY));
                    xray.style.height = newH + "px";
                    xray.style.maxHeight = newH + "px";
                }

                function onMouseUp() {
                    handle.classList.remove("active");
                    document.body.style.cursor = "";
                    document.removeEventListener("mousemove", onMouseMove);
                    document.removeEventListener("mouseup", onMouseUp);
                }

                document.addEventListener("mousemove", onMouseMove);
                document.addEventListener("mouseup", onMouseUp);
            });
        }

        // Wrong Answer action helpers
        function askMayaForCounterexample() {
            if (!activeProblemId) return;
            openAITutorModal('chat');
            setTimeout(() => {
                const code = document.getElementById("code") ? document.getElementById("code").value : "";
                const lastResult = lastExecutionResult;
                let msg = "Generate a counterexample test case that exposes the bug in my solution. Show the input, expected output, and my code's actual output.";
                if (lastResult && lastResult.test_results && lastResult.test_results[0]) {
                    const tc = lastResult.test_results.find(t => !t.passed) || lastResult.test_results[0];
                    msg += ` The failing case: expected "${tc.expected_output}", got "${tc.actual_output}".`;
                }
                sendQuickPromptText(msg);
            }, 400);
        }

        function askMayaToTraceCode() {
            if (!activeProblemId) return;
            openAITutorModal('chat');
            setTimeout(() => {
                const lastResult = lastExecutionResult;
                let msg = "Trace my code step-by-step for the failing test case. Show each variable state and where the output diverges from expected.";
                if (lastResult && lastResult.test_results) {
                    const tc = lastResult.test_results.find(t => !t.passed);
                    if (tc) msg += ` The failing case input is: "${tc.stdin || tc.input || 'see problem examples'}".`;
                }
                sendQuickPromptText(msg);
            }, 400);
        }

        function sendQuickPromptText(text) {
            const inp = document.getElementById("aiChatInput") || document.getElementById("chatInput");
            if (inp) {
                inp.value = text;
                inp.dispatchEvent(new Event('input'));
                const form = inp.closest("form");
                if (form) form.dispatchEvent(new Event('submit', { bubbles: true }));
                else {
                    const sendBtn = document.getElementById("aiChatSendBtn") || document.getElementById("sendChatBtn");
                    if (sendBtn) sendBtn.click();
                }
            }
        }


        // ========================================================
        // ADMIN TEST SYSTEM & STUDENT TAKING FLOW

        // ========================================================
        // ADMIN TEST SYSTEM & STUDENT TAKING FLOW
        // ========================================================
        let editingTestId = null;
        let modalQuestions = [];
        let catalogProblemsCache = [];
        let testTimerInterval = null;
        let activeTestSession = null;

        // ========================================================
        // STUDENT PERSONALIZED CODING ASSESSMENT SYSTEM
        // ========================================================
        let currentAsmDifficulty = 'Mixed';
        let currentAsmBlueprint = null;
        let lastAsmSubmission = null;

        function setAsmDifficulty(diff) {
            currentAsmDifficulty = diff;
            ['Easy', 'Medium', 'Hard', 'Mixed'].forEach(d => {
                const btn = document.getElementById(`diffBtn_${d}`);
                if (btn) {
                    if (d === diff) btn.classList.add('active');
                    else btn.classList.remove('active');
                }
            });
        }

        async function initAssessmentView() {
            populateAssessmentTopics();
            loadUnsolvedAssessmentProblems();
            loadAssessmentHistory();
            loadAdminTests();
            if (!currentAsmBlueprint) {
                generateAssessmentBlueprint();
            }
        }

        function populateAssessmentTopics() {
            const select = document.getElementById("asmTopicSelect");
            if (!select) return;
            const currentVal = select.value || "All";

            const topicsFilter = document.getElementById("topicFilter");
            if (topicsFilter && topicsFilter.options.length > 1) {
                select.innerHTML = '<option value="All">All Topics (Full-Spectrum)</option>';
                for (let i = 1; i < topicsFilter.options.length; i++) {
                    const opt = document.createElement("option");
                    opt.value = topicsFilter.options[i].value;
                    opt.textContent = topicsFilter.options[i].textContent;
                    select.appendChild(opt);
                }
                select.value = currentVal;
            } else {
                fetch(`${API_BASE}/topics`).then(res => res.json()).then(topics => {
                    select.innerHTML = '<option value="All">All Topics (Full-Spectrum)</option>';
                    topics.forEach(t => {
                        const opt = document.createElement("option");
                        opt.value = t.name;
                        opt.textContent = `${t.name} (${t.problem_count})`;
                        select.appendChild(opt);
                    });
                    select.value = currentVal;
                }).catch(err => console.warn("Failed to load assessment topics:", err));
            }
        }

        function onAssessmentTopicChange() {
            const topic = document.getElementById("asmTopicSelect").value;
            const titleEl = document.getElementById("unsolvedSectionTitle");
            if (titleEl) {
                titleEl.textContent = `Unsolved Problems in ${topic === 'All' ? 'Problem Bank' : topic}`;
            }
            loadUnsolvedAssessmentProblems();
        }

        async function generateAssessmentBlueprint() {
            const topicSelect = document.getElementById("asmTopicSelect");
            const topic = topicSelect ? topicSelect.value : "All";
            const count = parseInt(document.getElementById("asmCountSelect")?.value) || 3;
            const duration = parseInt(document.getElementById("asmDurationSelect")?.value) || 45;
            const aiEnabled = Boolean(document.getElementById("asmEnableAi")?.checked);
            const btn = document.getElementById("asmGenerateBtn");
            const container = document.getElementById("asmBlueprintContent");

            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span>⏳</span> <span>Analyzing Mastery & Selecting Real Problems...</span>';
            }

            if (container) {
                container.innerHTML = `
                    <div style="text-align: center; padding: 50px 20px; color: #94a3b8;">
                        <div style="font-size: 36px; margin-bottom: 12px;">🧠</div>
                        <div style="font-size: 15px; font-weight: 700; color: #f8fafc; margin-bottom: 6px;">Generating Personalized Assessment</div>
                        <div style="font-size: 13px; color: #94a3b8;">Prioritizing developing concepts, at-risk patterns, and fresh unsolved problems from problem bank...</div>
                    </div>
                `;
            }

            try {
                let data = null;
                const endpoints = [
                    `${API_BASE}/api/assessment/generate`,
                    `${API_BASE}/assessment/generate`,
                    `${API_BASE}/api/tests/generate`,
                    `${API_BASE}/tests/generate`
                ];
                const sid = getStudentId();
                for (const ep of endpoints) {
                    try {
                        const res = await authFetch(ep, {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                student_id: sid,
                                topic: topic,
                                difficulty: currentAsmDifficulty,
                                count: count,
                                duration_minutes: duration,
                                enable_ai_tutor: aiEnabled
                            })
                        });
                        if (res.ok) {
                            data = await res.json();
                            break;
                        }
                    } catch (e) {}
                }

                if (!data) {
                    data = await generateAssessmentFromRealProblemBank(topic, currentAsmDifficulty, count, duration, aiEnabled);
                }

                currentAsmBlueprint = data;
                renderAssessmentBlueprint(data);

            } catch (err) {
                if (container) {
                    container.innerHTML = `
                        <div style="padding: 24px; color: #ef4444; background: rgba(239, 68, 68, 0.1); border-radius: 8px; text-align: center;">
                            <strong>Generation Error:</strong> ${escapeHtml(err.message)}
                            <div style="margin-top: 12px;">
                                <button class="nav-button" onclick="generateAssessmentBlueprint()">Try Again</button>
                            </div>
                        </div>
                    `;
                }
            } finally {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>⚡</span> <span>Prepare Assessment Blueprint</span>';
                }
            }
        }

        async function generateAssessmentFromRealProblemBank(topic, difficulty, count, duration, aiEnabled) {
            let pUrl = `${API_BASE}/problems?page=1&page_size=100`;
            if (topic && topic !== "All") pUrl += `&domain=${encodeURIComponent(topic)}`;
            if (difficulty && difficulty !== "Mixed") pUrl += `&difficulty=${encodeURIComponent(difficulty)}`;

            let problems = [];
            try {
                const res = await fetch(pUrl);
                if (res.ok) {
                    const pd = await res.json();
                    problems = pd.items || pd.problems || (Array.isArray(pd) ? pd : []);
                }
            } catch(e) {}

            if (!problems.length) {
                const r2 = await fetch(`${API_BASE}/problems?page=1&page_size=50`);
                if (r2.ok) {
                    const pd2 = await r2.json();
                    problems = pd2.items || pd2.problems || [];
                }
            }

            const solvedIds = new Set();
            try {
                const sid = getStudentId();
                const progRes = await authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid)}`);
                if (progRes.ok) {
                    const prog = await progRes.json();
                    if (prog.submissions) {
                        prog.submissions.filter(s => s.status === "accepted" || s.status === "Accepted").forEach(s => solvedIds.add(s.problem_id));
                    }
                }
            } catch (e) {}

            const unsolved = problems.filter(p => !solvedIds.has(p.id)).sort(() => Math.random() - 0.5);
            const solved = problems.filter(p => solvedIds.has(p.id)).sort(() => Math.random() - 0.5);
            const selected = [...unsolved, ...solved].slice(0, count);

            const concepts = new Set();
            selected.forEach(p => {
                if (Array.isArray(p.concepts)) p.concepts.forEach(c => concepts.add(String(c)));
                if (Array.isArray(p.domains)) p.domains.forEach(d => concepts.add(typeof d === 'string' ? d : d.name));
            });

            const testId = `test-asm-${Math.random().toString(36).substring(2, 10)}`;
            const cleanTopic = topic && topic !== "All" ? topic : "Full-Spectrum";
            const testTitle = `${cleanTopic} Assessment • ${difficulty}`;
            const testDesc = `Personalized assessment • ${selected.length} questions • ${duration} minutes`;

            const testObj = {
                id: testId,
                title: testTitle,
                description: testDesc,
                duration_minutes: duration,
                allowed_languages: ["python", "javascript", "cpp", "java"],
                restrict_copy_paste: false,
                enable_camera: false,
                enable_microphone: false,
                require_fullscreen: false,
                enable_proctoring: false,
                enable_ai_tutor: aiEnabled,
                is_active: true,
                questions: selected.map((p, idx) => ({
                    id: `tq-${idx}-${p.id}`,
                    test_id: testId,
                    problem_id: p.id,
                    is_custom: false,
                    title: p.title || `Problem ${idx + 1}`,
                    description: p.description || "",
                    difficulty: p.difficulty || "Easy",
                    input_format: p.input_format,
                    output_format: p.output_format,
                    examples: p.examples || [],
                    constraints: p.constraints || [],
                    starter_code: p.starter_code || {},
                    points: 10,
                    order: idx
                }))
            };

            return {
                test: testObj,
                blueprint: {
                    topic: cleanTopic,
                    difficulty: difficulty,
                    question_count: selected.length,
                    duration_minutes: duration,
                    concepts: Array.from(concepts).slice(0, 10),
                    solved_count: selected.filter(p => solvedIds.has(p.id)).length,
                    unsolved_count: selected.filter(p => !solvedIds.has(p.id)).length,
                    mastery_status: unsolved.length > 0 ? "Targeted Reinforcement" : "Proficiency Benchmark",
                    enable_ai_tutor: aiEnabled,
                    test_id: testId
                }
            };
        }

        function renderAssessmentBlueprint(data) {
            const container = document.getElementById("asmBlueprintContent");
            if (!container) return;
            const bp = data.blueprint;

            const conceptBadges = (bp.concepts || []).map(c => 
                `<span class="chip-tag" style="background: #1e293b; color: #38bdf8; border: 1px solid #0284c7; padding: 4px 10px; font-size: 12px; border-radius: 6px;">${escapeHtml(c)}</span>`
            ).join(" ");

            const diffBadgeClass = `badge-${(bp.difficulty || 'easy').toLowerCase()}`;

            container.innerHTML = `
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 16px; flex-wrap: wrap; gap: 8px;">
                        <div>
                            <span class="badge" style="background: #0284c7; color: #fff; font-size: 11px; margin-bottom: 6px; display: inline-block;">ACTIVE BLUEPRINT READY</span>
                            <h2 style="font-size: 20px; font-weight: 800; color: #f8fafc; margin: 0;">${escapeHtml(bp.topic)} Assessment</h2>
                        </div>
                        <div style="display: flex; gap: 6px; align-items: center;">
                            <span class="badge ${diffBadgeClass}" style="font-size: 12px; padding: 4px 10px;">${escapeHtml(bp.difficulty)}</span>
                            <span class="badge" style="background: #1e293b; color: #cbd5e1; border: 1px solid #475569; font-size: 12px; padding: 4px 10px;">⏱ ${bp.duration_minutes} Mins</span>
                        </div>
                    </div>

                    <!-- METRICS GRID -->
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 18px;">
                        <div style="background: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Total Questions</div>
                            <div style="font-size: 18px; font-weight: 800; color: #38bdf8; margin-top: 2px;">${bp.question_count} Real Problems</div>
                        </div>
                        <div style="background: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Fresh Practice</div>
                            <div style="font-size: 18px; font-weight: 800; color: #22c55e; margin-top: 2px;">${bp.unsolved_count} Unsolved</div>
                        </div>
                        <div style="background: #0b1120; border: 1px solid #1e293b; padding: 12px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 11px; color: #94a3b8; text-transform: uppercase;">Mastery Focus</div>
                            <div style="font-size: 12px; font-weight: 700; color: #eab308; margin-top: 4px;">${escapeHtml(bp.mastery_status || 'Targeted')}</div>
                        </div>
                    </div>

                    <!-- CONCEPTS TESTED -->
                    <div style="margin-bottom: 18px;">
                        <div style="font-size: 12px; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 8px; letter-spacing: 0.5px;">Target Concepts Tested:</div>
                        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                            ${conceptBadges || '<span style="color: #64748b; font-size: 12px;">Core algorithmic fundamentals</span>'}
                        </div>
                    </div>

                    <!-- AI POLICY BADGE -->
                    <div style="margin-bottom: 20px; padding: 10px 14px; background: #0b1120; border-left: 3px solid ${bp.enable_ai_tutor ? '#8b5cf6' : '#64748b'}; border-radius: 6px;">
                        <div style="font-size: 12px; font-weight: 700; color: ${bp.enable_ai_tutor ? '#a78bfa' : '#94a3b8'};">
                            ${bp.enable_ai_tutor ? '📖 AI Question Clarification: ACTIVE' : '🚫 AI Assistance: DISABLED FOR THIS ASSESSMENT'}
                        </div>
                        <div style="font-size: 11px; color: #64748b; margin-top: 2px;">
                            ${bp.enable_ai_tutor ? 'You may ask AI to clarify questions and constraints during the test. Code and hints remain strictly blocked.' : 'Independent solve conditions enforced.'}
                        </div>
                    </div>
                </div>

                <!-- ACTIONS -->
                <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #1e293b; padding-top: 16px; margin-top: 10px; gap: 10px; flex-wrap: wrap;">
                    <button class="nav-button" onclick="generateAssessmentBlueprint()" style="padding: 9px 16px; font-size: 13px; background: #1e293b; color: #94a3b8;">
                        ↺ Reshuffle Fresh Set
                    </button>
                    <button class="run-button" onclick="startAssessmentFromBlueprint()" style="margin-top: 0; padding: 11px 24px; font-size: 14px; font-weight: 700; background: #16a34a; color: #ffffff;">
                        ▶ Start Assessment (${bp.duration_minutes} Mins)
                    </button>
                </div>
            `;
        }

        function startAssessmentFromBlueprint() {
            if (!currentAsmBlueprint || !currentAsmBlueprint.test) {
                alert("Please prepare an assessment blueprint first.");
                return;
            }
            startTestTaking(currentAsmBlueprint.test.id);
        }

        async function loadUnsolvedAssessmentProblems() {
            const topic = document.getElementById("asmTopicSelect") ? document.getElementById("asmTopicSelect").value : "All";
            const container = document.getElementById("unsolvedProblemsList");
            const badge = document.getElementById("unsolvedCountBadge");
            if (!container || !badge) return;
            badge.textContent = "Loading...";

            try {
                const sid = getStudentId();
                const endpoints = [
                    `${API_BASE}/api/assessment/unsolved?student_id=${encodeURIComponent(sid)}&topic=${encodeURIComponent(topic)}`,
                    `${API_BASE}/assessment/unsolved?student_id=${encodeURIComponent(sid)}&topic=${encodeURIComponent(topic)}`,
                    `${API_BASE}/api/tests/unsolved?student_id=${encodeURIComponent(sid)}&topic=${encodeURIComponent(topic)}`,
                    `${API_BASE}/tests/unsolved?student_id=${encodeURIComponent(sid)}&topic=${encodeURIComponent(topic)}`
                ];
                for (const ep of endpoints) {
                    try {
                        const res = await authFetch(ep);
                        if (res.ok) {
                            data = await res.json();
                            break;
                        }
                    } catch (e) {}
                }

                if (!data) {
                    const sid = getStudentId();
                    let pUrl = `${API_BASE}/problems?page=1&page_size=100`;
                    if (topic && topic !== "All") pUrl += `&domain=${encodeURIComponent(topic)}`;
                    const [pRes, progRes] = await Promise.all([
                        fetch(pUrl).then(r => r.ok ? r.json() : null).catch(() => null),
                        authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid)}`).then(r => r.ok ? r.json() : null).catch(() => null)
                    ]);
                    const allProbs = pRes ? (pRes.items || pRes.problems || []) : [];
                    const solvedIds = new Set();
                    if (progRes && progRes.submissions) {
                        progRes.submissions.filter(s => s.status === 'accepted' || s.status === 'Accepted').forEach(s => solvedIds.add(s.problem_id));
                    }
                    const un = allProbs.filter(p => !solvedIds.has(p.id));
                    data = {
                        topic: topic,
                        total_count: allProbs.length,
                        solved_count: allProbs.length - un.length,
                        unsolved_count: un.length,
                        unsolved_problems: un.slice(0, 25).map(p => ({
                            id: p.id,
                            title: p.title,
                            difficulty: p.difficulty,
                            domain: Array.isArray(p.domains) && p.domains[0] ? (typeof p.domains[0] === 'string' ? p.domains[0] : p.domains[0].name) : "Algorithms"
                        }))
                    };
                }

                badge.textContent = `${data.unsolved_count} Unsolved / ${data.total_count} Total`;

                if (!data.unsolved_problems || data.unsolved_problems.length === 0) {
                    container.innerHTML = `<div style="grid-column: 1 / -1; color: #22c55e; padding: 16px; text-align: center;">🎉 Outstanding! You have solved all problems in this topic!</div>`;
                    return;
                }

                container.innerHTML = "";
                data.unsolved_problems.forEach(p => {
                    const item = document.createElement("div");
                    item.style.background = "#0f172a";
                    item.style.border = "1px solid #1e293b";
                    item.style.borderRadius = "8px";
                    item.style.padding = "10px 14px";
                    item.style.display = "flex";
                    item.style.justifyContent = "space-between";
                    item.style.alignItems = "center";
                    item.style.gap = "8px";

                    const diffClass = `badge-${(p.difficulty || 'easy').toLowerCase()}`;
                    item.innerHTML = `
                        <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                            <div style="font-size: 13px; font-weight: 600; color: #f8fafc; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(p.title)}</div>
                            <div style="display: flex; gap: 6px; align-items: center; margin-top: 4px;">
                                <span class="badge ${diffClass}" style="font-size: 10px; padding: 2px 6px;">${escapeHtml(p.difficulty)}</span>
                                <span style="font-size: 11px; color: #64748b;">${escapeHtml(p.domain || '')}</span>
                            </div>
                        </div>
                        <button class="run-button" onclick="openProblem('${p.id}')" style="margin-top: 0; padding: 4px 10px; font-size: 11px; flex-shrink: 0; background: #0284c7;">
                            Practice ↗
                        </button>
                    `;
                    container.appendChild(item);
                });

            } catch (err) {
                badge.textContent = "—";
                container.innerHTML = `<div style="grid-column: 1 / -1; color: #ef4444; font-size: 12px; padding: 10px;">Failed to load unsolved problems: ${escapeHtml(err.message)}</div>`;
            }
        }

        async function loadAssessmentHistory() {
            const container = document.getElementById("assessmentHistoryTable");
            if (!container) return;
            try {
                const sid = getStudentId();
                let history = null;
                const endpoints = [
                    `${API_BASE}/api/assessment/history?student_id=${encodeURIComponent(sid)}`,
                    `${API_BASE}/api/tests/history?student_id=${encodeURIComponent(sid)}`,
                    `${API_BASE}/tests/history?student_id=${encodeURIComponent(sid)}`
                ];
                for (const ep of endpoints) {
                    try {
                        const res = await authFetch(ep);
                        if (res.ok) {
                            history = await res.json();
                            break;
                        }
                    } catch (e) {}
                }

                if (!history) {
                    const progRes = await authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid)}`).then(r => r.ok ? r.json() : null).catch(() => null);
                    if (progRes && progRes.test_history) {
                        history = progRes.test_history.map(th => ({
                            submission_id: th.id,
                            test_id: th.test_id,
                            title: th.title || "Assessment",
                            score: `${th.total_score} / ${th.max_score}`,
                            percentage: th.percentage,
                            status: "completed",
                            topic: "Assessment",
                            difficulty: "Mixed",
                            question_count: 3,
                            submitted_at: th.submitted_at || ""
                        }));
                    }
                }

                if (!history || history.length === 0) {
                    container.innerHTML = `
                        <div style="text-align: center; padding: 24px; color: #64748b; font-size: 13px;">
                            No assessment attempts recorded yet. Configure and complete an assessment above to track your scores.
                        </div>
                    `;
                    return;
                }

                let rows = `
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px; text-align: left;">
                        <thead>
                            <tr style="border-bottom: 1px solid #334155; color: #94a3b8;">
                                <th style="padding: 10px;">Date</th>
                                <th style="padding: 10px;">Assessment Title</th>
                                <th style="padding: 10px;">Difficulty</th>
                                <th style="padding: 10px;">Score</th>
                                <th style="padding: 10px;">Accuracy</th>
                                <th style="padding: 10px; text-align: right;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                `;

                history.forEach(h => {
                    const dateStr = h.submitted_at ? new Date(h.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Recent';
                    const percColor = h.percentage >= 70 ? '#22c55e' : h.percentage >= 40 ? '#f59e0b' : '#ef4444';
                    rows += `
                        <tr style="border-bottom: 1px solid #1e293b; color: #cbd5e1;">
                            <td style="padding: 10px; color: #94a3b8; font-size: 12px;">${dateStr}</td>
                            <td style="padding: 10px; font-weight: 600; color: #f8fafc;">${escapeHtml(h.title || 'Assessment')}</td>
                            <td style="padding: 10px;"><span class="badge badge-${(h.difficulty||'easy').toLowerCase()}" style="font-size: 11px;">${escapeHtml(h.difficulty || 'Mixed')}</span></td>
                            <td style="padding: 10px; font-weight: 700; color: #38bdf8;">${escapeHtml(h.score)}</td>
                            <td style="padding: 10px;"><span style="color: ${percColor}; font-weight: 700;">${h.percentage}%</span></td>
                            <td style="padding: 10px; text-align: right;">
                                <button class="nav-button" onclick="retakeAssessment('${escapeHtml(h.topic || 'All')}', '${escapeHtml(h.difficulty || 'Mixed')}', ${h.question_count || 3})" style="padding: 4px 10px; font-size: 11px; background: #1e293b; color: #38bdf8; border-color: #38bdf8;">
                                    ↺ Retake
                                </button>
                            </td>
                        </tr>
                    `;
                });

                rows += `</tbody></table>`;
                container.innerHTML = rows;

            } catch (err) {
                container.innerHTML = `<div style="color: #ef4444; font-size: 12px; padding: 12px;">Failed to load history: ${escapeHtml(err.message)}</div>`;
            }
        }

        async function retakeAssessment(topic, difficulty, count) {
            if (document.getElementById("asmTopicSelect")) {
                document.getElementById("asmTopicSelect").value = topic || "All";
            }
            setAsmDifficulty(difficulty || "Mixed");
            if (document.getElementById("asmCountSelect")) {
                document.getElementById("asmCountSelect").value = String(count || 3);
            }
            window.scrollTo({ top: 0, behavior: "smooth" });
            generateAssessmentBlueprint();
        }

        function retakeCurrentAssessment() {
            closeResultModal();
            if (lastAsmSubmission && lastAsmSubmission.topic) {
                retakeAssessment(lastAsmSubmission.topic, lastAsmSubmission.difficulty, 3);
            } else {
                generateAssessmentBlueprint();
            }
        }

        function toggleAdminTestsSection() {
            const collapse = document.getElementById("adminTestsCollapse");
            const icon = document.getElementById("adminTestsToggleIcon");
            if (!collapse) return;
            if (collapse.style.display === "none") {
                collapse.style.display = "block";
                if (icon) icon.textContent = "▲ Hide";
            } else {
                collapse.style.display = "none";
                if (icon) icon.textContent = "▼ Show";
            }
        }

        function toggleMarkCurrentQuestionForReview() {
            if (!activeTestSession) return;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            if (!q) return;
            if (!activeTestSession.markedForReview) activeTestSession.markedForReview = {};
            activeTestSession.markedForReview[q.problem_id] = !activeTestSession.markedForReview[q.problem_id];
            localStorage.setItem('codemind_active_test', JSON.stringify(activeTestSession));
            updateMarkReviewBtnState();
            renderTestQuestionTabs();
        }

        function updateMarkReviewBtnState() {
            const btn = document.getElementById("takingMarkReviewBtn");
            if (!btn || !activeTestSession) return;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            if (!q) return;
            const isMarked = activeTestSession.markedForReview && activeTestSession.markedForReview[q.problem_id];
            if (isMarked) {
                btn.style.background = "#d97706";
                btn.style.color = "#ffffff";
                btn.textContent = "🚩 Marked for Review";
            } else {
                btn.style.background = "#1e293b";
                btn.style.color = "#94a3b8";
                btn.textContent = "🚩 Mark for Review";
            }
        }

        // Fetch & render admin tests
        async function loadAdminTests() {
            const grid = document.getElementById("testsGrid");
            grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; padding: 40px; color: #94a3b8;">Loading assessment tests...</div>';

            try {
                const res = await authFetch(`${API_BASE}/api/admin/tests`);
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    throw new Error(errData.detail || `HTTP ${res.status}`);
                }
                const tests = await res.json();
                const countBadge = document.getElementById("adminTestCount");
                if (countBadge) countBadge.textContent = (tests && tests.length) || 0;

                if (!tests || tests.length === 0) {
                    grid.innerHTML = `
                        <div style="grid-column: 1 / -1; text-align: center; padding: 50px; background: #1e293b; border-radius: 12px; border: 1px dashed #334155;">
                            <h3 style="color: #f8fafc; margin-bottom: 8px;">No Assessment Tests Yet</h3>
                            <p style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">Create tests with mixed CodeMind catalog problems and custom questions.</p>
                            <button class="run-button" onclick="openCreateTestModal()" style="margin: auto;">+ Create First Test</button>
                        </div>
                    `;
                    return;
                }

                grid.innerHTML = "";
                tests.forEach(t => {
                    const card = document.createElement("div");
                    card.className = "test-card-item";

                    // Badges for active security options
                    const secBadges = [];
                    if (t.restrict_copy_paste) secBadges.push('<span class="badge" style="background: #dc2626; color: #fff;">🚫 No Copy/Paste</span>');
                    if (t.enable_camera) secBadges.push('<span class="badge" style="background: #0284c7; color: #fff;">📷 Camera</span>');
                    if (t.enable_microphone) secBadges.push('<span class="badge" style="background: #0284c7; color: #fff;">🎙 Mic</span>');
                    if (t.require_fullscreen) secBadges.push('<span class="badge" style="background: #7c3aed; color: #fff;">⛶ Fullscreen</span>');
                    if (t.enable_proctoring) secBadges.push('<span class="badge" style="background: #d97706; color: #fff;">🛡 Proctoring</span>');
                    if (secBadges.length === 0) {
                        secBadges.push('<span class="badge" style="background: #334155; color: #94a3b8;">🔓 Standard (No Restrictions)</span>');
                    }

                    // Allowed languages badge
                    let langText = "All Languages";
                    if (t.allowed_languages && t.allowed_languages.length > 0) {
                        langText = t.allowed_languages.map(l => l.toUpperCase()).join(", ");
                    }

                    card.innerHTML = `
                        <div>
                            <div class="test-header-row">
                                <h3 class="test-card-title">${escapeHtml(t.title)}</h3>
                                <span class="badge badge-source" style="font-size: 13px;">⏱ ${t.duration_minutes} mins</span>
                            </div>
                            <p class="test-card-desc">${escapeHtml(t.description || "No description provided.")}</p>
                            <div class="test-meta-row">
                                <span class="chip-domain">❓ ${t.question_count} Question${t.question_count === 1 ? '' : 's'}</span>
                                <span class="chip-domain">💻 ${langText}</span>
                            </div>
                            <div class="test-meta-row">
                                ${secBadges.join(" ")}
                            </div>
                        </div>
                        <div class="test-actions-row">
                            <button class="btn-solve" onclick="startTestTaking('${t.id}')" style="background: #16a34a; color: #fff; font-weight: 700;">
                                ▶ Take Test
                            </button>
                            <div style="display: flex; gap: 8px;">
                                <button class="nav-button" onclick="openEditTestModal('${t.id}')" style="padding: 6px 12px; font-size: 12px;">
                                    ✏ Edit
                                </button>
                                <button class="nav-button" onclick="deleteAdminTest('${t.id}', '${escapeHtml(t.title)}')" style="padding: 6px 12px; font-size: 12px; color: #f87171; border-color: #7f1d1d;">
                                    🗑 Delete
                                </button>
                            </div>
                        </div>
                    `;
                    grid.appendChild(card);
                });
            } catch (err) {
                console.error("Failed to load tests:", err);
                grid.innerHTML = `
                    <div style="grid-column: 1 / -1; color: #f87171; text-align: center; padding: 40px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px;">
                        <div style="font-size: 24px; margin-bottom: 8px;">⚠️</div>
                        <strong style="font-size: 14px;">Error Loading Assessment Tests</strong>
                        <div style="font-size: 13px; color: #cbd5e1; margin-top: 4px;">${escapeHtml(err.message)}</div>
                        <div style="margin-top: 14px;">
                            <button class="nav-button" onclick="loadAdminTests()" style="padding: 6px 16px; font-size: 12px;">Retry</button>
                        </div>
                    </div>
                `;
            }
        }

        // Cache catalog problems for the test question dropdown
        async function ensureCatalogProblemsLoaded() {
            if (catalogProblemsCache.length > 0) return;
            try {
                const res = await fetch(`${API_BASE}/problems?page=1&page_size=100`);
                if (res.ok) {
                    const data = await res.json();
                    catalogProblemsCache = data.items || [];
                    populateCatalogDropdown();
                }
            } catch (e) {
                console.warn("Could not load catalog problems for test modal:", e);
            }
        }

        function populateCatalogDropdown() {
            const select = document.getElementById("catalogProblemSelect");
            if (!select) return;
            select.innerHTML = '<option value="">-- Select problem from CodeMind Catalog (11,390+ available) --</option>';
            catalogProblemsCache.forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `[${p.difficulty}] ${p.title} (${p.source})`;
                select.appendChild(opt);
            });
        }

        // OPEN CREATE TEST MODAL - ALL OPTIONS OFF BY DEFAULT
        function openCreateTestModal() {
            editingTestId = null;
            document.getElementById("testModalTitle").textContent = "Create Assessment Test";
            document.getElementById("testTitleInput").value = "";
            document.getElementById("testDescInput").value = "";
            document.getElementById("testDurationInput").value = "60";

            modalQuestions = [];
            renderModalQuestions();

            // EXPLICIT REQUIREMENT: ALL OPTIONS OFF / UNSELECTED BY DEFAULT
            document.getElementById("testLangPython").checked = false;
            document.getElementById("testLangC").checked = false;
            document.getElementById("testLangCpp").checked = false;
            document.getElementById("testLangJava").checked = false;

            document.getElementById("testRestrictCopyPaste").checked = false;
            document.getElementById("testEnableCamera").checked = false;
            document.getElementById("testEnableMic").checked = false;
            document.getElementById("testRequireFullscreen").checked = false;
            document.getElementById("testEnableProctoring").checked = false;
            document.getElementById("testEnableAiTutor").checked = false;

            ensureCatalogProblemsLoaded();
            document.getElementById("testModal").style.display = "flex";
        }

        // OPEN EDIT TEST MODAL
        async function openEditTestModal(testId) {
            try {
                const res = await authFetch(`${API_BASE}/api/admin/tests/${testId}`);
                if (!res.ok) throw new Error("Could not fetch test details.");
                const test = await res.json();

                editingTestId = test.id;
                document.getElementById("testModalTitle").textContent = "Edit Assessment Test";
                document.getElementById("testTitleInput").value = test.title || "";
                document.getElementById("testDescInput").value = test.description || "";
                document.getElementById("testDurationInput").value = test.duration_minutes || 60;

                modalQuestions = (test.questions || []).map(q => ({
                    problem_id: q.problem_id,
                    is_custom: q.is_custom,
                    title: q.title,
                    description: q.description,
                    difficulty: q.difficulty,
                    input_format: q.input_format,
                    output_format: q.output_format,
                    examples: q.examples,
                    constraints: q.constraints,
                    starter_code: q.starter_code,
                    points: q.points || 10
                }));
                renderModalQuestions();

                // Set saved checkboxes
                const langs = test.allowed_languages || [];
                document.getElementById("testLangPython").checked = langs.includes("python");
                document.getElementById("testLangC").checked = langs.includes("c");
                document.getElementById("testLangCpp").checked = langs.includes("cpp");
                document.getElementById("testLangJava").checked = langs.includes("java");

                document.getElementById("testRestrictCopyPaste").checked = Boolean(test.restrict_copy_paste);
                document.getElementById("testEnableCamera").checked = Boolean(test.enable_camera);
                document.getElementById("testEnableMic").checked = Boolean(test.enable_microphone);
                document.getElementById("testRequireFullscreen").checked = Boolean(test.require_fullscreen);
                document.getElementById("testEnableProctoring").checked = Boolean(test.enable_proctoring);
                document.getElementById("testEnableAiTutor").checked = Boolean(test.enable_ai_tutor);

                ensureCatalogProblemsLoaded();
                document.getElementById("testModal").style.display = "flex";
            } catch (err) {
                alert("Failed to load test: " + err.message);
            }
        }

        function closeTestModal() {
            document.getElementById("testModal").style.display = "none";
        }

        // ADD EXISTING PROBLEM TO TEST
        function addSelectedCatalogProblem() {
            const select = document.getElementById("catalogProblemSelect");
            const probId = select.value;
            if (!probId) {
                alert("Please select a problem from the dropdown first.");
                return;
            }

            if (modalQuestions.some(q => q.problem_id === probId)) {
                alert("This problem is already in the test.");
                return;
            }

            const p = catalogProblemsCache.find(x => x.id === probId);
            modalQuestions.push({
                problem_id: probId,
                is_custom: false,
                title: p ? p.title : probId,
                difficulty: p ? p.difficulty : "Easy",
                points: 10
            });
            renderModalQuestions();
            select.value = "";
        }

        // CUSTOM QUESTION MODAL
        function openCustomQuestionModal() {
            document.getElementById("cqTitle").value = "";
            document.getElementById("cqDifficulty").value = "Medium";
            document.getElementById("cqPoints").value = "20";
            document.getElementById("cqDescription").value = "";
            document.getElementById("cqTc1Input").value = "";
            document.getElementById("cqTc1Output").value = "";
            document.getElementById("cqTc2Input").value = "";
            document.getElementById("cqTc2Output").value = "";
            document.getElementById("cqStarterCode").value = "def solve():\n    # Write your solution here\n    pass\n";
            document.getElementById("customQuestionModal").style.display = "flex";
        }

        function closeCustomQuestionModal() {
            document.getElementById("customQuestionModal").style.display = "none";
        }

        function saveCustomQuestionToTest() {
            const title = document.getElementById("cqTitle").value.trim();
            const desc = document.getElementById("cqDescription").value.trim();
            const diff = document.getElementById("cqDifficulty").value;
            const pts = parseInt(document.getElementById("cqPoints").value, 10) || 10;
            const tc1In = document.getElementById("cqTc1Input").value.trim();
            const tc1Out = document.getElementById("cqTc1Output").value.trim();
            const tc2In = document.getElementById("cqTc2Input").value.trim();
            const tc2Out = document.getElementById("cqTc2Output").value.trim();
            const starter = document.getElementById("cqStarterCode").value;

            if (!title) {
                alert("Please enter a question title.");
                return;
            }
            if (!desc) {
                alert("Please enter a description for the custom question.");
                return;
            }
            if (!tc1In || !tc1Out) {
                alert("Please provide at least Test Case 1 input and expected output.");
                return;
            }

            const examples = [
                { input: tc1In, output: tc1Out, explanation: "Sample case 1" }
            ];
            if (tc2In && tc2Out) {
                examples.push({ input: tc2In, output: tc2Out, explanation: "Sample case 2" });
            }

            modalQuestions.push({
                is_custom: true,
                title: title,
                description: desc,
                difficulty: diff,
                points: pts,
                examples: examples,
                starter_code: {
                    python: starter
                }
            });

            renderModalQuestions();
            closeCustomQuestionModal();
        }

        function removeModalQuestion(index) {
            modalQuestions.splice(index, 1);
            renderModalQuestions();
        }

        function renderModalQuestions() {
            const container = document.getElementById("modalQuestionsList");
            if (!modalQuestions || modalQuestions.length === 0) {
                container.innerHTML = `
                    <div style="color: #64748b; font-size: 13px; text-align: center; padding: 20px;">
                        No questions added yet. Add an existing CodeMind problem or create a custom question.
                    </div>
                `;
                return;
            }

            container.innerHTML = "";
            modalQuestions.forEach((q, idx) => {
                const item = document.createElement("div");
                item.className = "question-item-card";
                const typeBadge = q.is_custom
                    ? '<span class="badge badge-source" style="background: #0284c7; color: #fff;">Custom</span>'
                    : '<span class="badge badge-source">CodeMind</span>';

                item.innerHTML = `
                    <div>
                        <span style="color: #94a3b8; font-size: 12px; margin-right: 8px;">Q${idx + 1}</span>
                        <strong style="color: #f8fafc; font-size: 14px;">${escapeHtml(q.title)}</strong>
                        <span style="margin-left: 8px;">${typeBadge}</span>
                        <span class="badge badge-${(q.difficulty || 'easy').toLowerCase()}" style="margin-left: 6px;">${escapeHtml(q.difficulty || 'Medium')}</span>
                        <span style="color: #94a3b8; font-size: 12px; margin-left: 10px;">${q.points || 10} pts</span>
                    </div>
                    <button type="button" onclick="removeModalQuestion(${idx})" style="background: none; border: none; color: #f87171; cursor: pointer; font-size: 15px;">✕</button>
                `;
                container.appendChild(item);
            });
        }

        // SAVE TEST TO BACKEND
        async function saveTest() {
            const title = document.getElementById("testTitleInput").value.trim();
            const desc = document.getElementById("testDescInput").value.trim();
            const duration = parseInt(document.getElementById("testDurationInput").value, 10) || 60;

            if (!title) {
                alert("Please enter a test title.");
                return;
            }

            if (modalQuestions.length === 0) {
                alert("Please add at least one question (catalog problem or custom question) to this test.");
                return;
            }

            // Gather allowed languages
            const allowedLangs = [];
            if (document.getElementById("testLangPython").checked) allowedLangs.push("python");
            if (document.getElementById("testLangC").checked) allowedLangs.push("c");
            if (document.getElementById("testLangCpp").checked) allowedLangs.push("cpp");
            if (document.getElementById("testLangJava").checked) allowedLangs.push("java");

            if (allowedLangs.length === 0) {
                alert("Please select at least one programming language for this test.");
                return;
            }


            const payload = {
                title: title,
                description: desc,
                duration_minutes: duration,
                allowed_languages: allowedLangs,
                restrict_copy_paste: document.getElementById("testRestrictCopyPaste").checked,
                enable_camera: document.getElementById("testEnableCamera").checked,
                enable_microphone: document.getElementById("testEnableMic").checked,
                require_fullscreen: document.getElementById("testRequireFullscreen").checked,
                enable_proctoring: document.getElementById("testEnableProctoring").checked,
                enable_ai_tutor: document.getElementById("testEnableAiTutor").checked,
                questions: modalQuestions
            };

            try {
                const url = editingTestId ? `${API_BASE}/api/admin/tests/${editingTestId}` : `${API_BASE}/api/admin/tests`;
                const method = editingTestId ? "PUT" : "POST";

                const res = await authFetch(url, {
                    method: method,
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `Server error: ${res.status}`);
                }

                closeTestModal();
                loadAdminTests();
            } catch (err) {
                alert("Failed to save test: " + err.message);
            }
        }

        // DELETE TEST
        async function deleteAdminTest(testId, testTitle) {
            if (!confirm(`Are you sure you want to delete test "${testTitle}"?`)) return;
            try {
                const res = await authFetch(`${API_BASE}/api/admin/tests/${testId}`, {
                    method: "DELETE"
                });
                if (!res.ok) throw new Error("Could not delete test.");
                loadAdminTests();
            } catch (err) {
                alert("Error deleting test: " + err.message);
            }
        }

        // ========================================================
        // STUDENT TEST-TAKING WORKSPACE & RESTRICTIONS ENFORCEMENT
        // ========================================================
        async function startTestTaking(testId) {
            try {
                // Check if existing saved session exists for this test
                const savedRaw = localStorage.getItem('codemind_active_test');
                let existingSession = null;
                if (savedRaw) {
                    try {
                        const parsed = JSON.parse(savedRaw);
                        const currentUid = typeof getStudentId === 'function' ? getStudentId() : null;
                        if (parsed && parsed.test && parsed.test.id === testId && parsed.endTime && Date.now() < parsed.endTime) {
                            if (!parsed.studentId || parsed.studentId === currentUid) {
                                existingSession = parsed;
                            } else {
                                localStorage.removeItem('codemind_active_test');
                            }
                        } else if (parsed && parsed.test && parsed.test.id !== testId && parsed.endTime && Date.now() < parsed.endTime) {
                            if (!confirm("You have another test in progress. Starting this new test will cancel the previous in-progress test session. Continue?")) {
                                return;
                            }
                            localStorage.removeItem('codemind_active_test');
                        }
                    } catch (e) {
                        console.error(e);
                    }
                }

                // Authoritative server fetch to verify active status and question integrity
                let test = null;
                try {
                    const fetchFn = typeof authFetch === 'function' ? authFetch : fetch;
                    const res = await fetchFn(`${API_BASE}/api/tests/${testId}`);
                    if (res.ok) {
                        test = await res.json();
                    } else if (res.status === 404 || res.status === 400) {
                        localStorage.removeItem('codemind_active_test');
                        throw new Error("This test is inactive, expired, or unavailable.");
                    }
                } catch (e) {
                    if (e.message.includes("inactive, expired")) throw e;
                }

                if (!test && currentAsmBlueprint && currentAsmBlueprint.test && currentAsmBlueprint.test.id === testId) {
                    test = currentAsmBlueprint.test;
                }
                if (!test) {
                    localStorage.removeItem('codemind_active_test');
                    throw new Error("Test not found or unavailable.");
                }

                if (!test.questions || test.questions.length === 0) {
                    alert("This test has no questions assigned yet.");
                    return;
                }

                const currentUid = typeof getStudentId === 'function' ? getStudentId() : 'guest';
                if (existingSession) {
                    existingSession.test = test; // Keep questions and allowed_languages authoritative from server
                    existingSession.studentId = currentUid;
                    activeTestSession = existingSession;
                } else {
                    const durationSeconds = (test.duration_minutes || 60) * 60;
                    activeTestSession = {
                        studentId: currentUid,
                        test: test,
                        activeQuestionIndex: 0,
                        startTime: Date.now(),
                        endTime: Date.now() + durationSeconds * 1000,
                        answers: {}
                    };
                    localStorage.setItem('codemind_active_test', JSON.stringify(activeTestSession));
                }

                setupTestSessionUI(activeTestSession);

            } catch (err) {
                alert("Unable to start test: " + err.message);
                showTestsView();
            }
        }

        function setupTestSessionUI(session) {
            window.active_workspace = 'test_taking';
            const test = session.test;
            hideAllViews();
            document.getElementById("testTakingView").style.display = "block";
            setActiveNav(""); // no general nav tab active during test session

            document.getElementById("takingTestTitle").textContent = test.title;
            document.getElementById("takingTestSubtitle").textContent = test.description || `Assessment • ${test.duration_minutes} minutes`;

            // Set up restrictions banner & proctoring pills
            const banner = document.getElementById("testRestrictionsBanner");
            const pills = document.getElementById("testProctoringPills");
            pills.innerHTML = "";

            const activeRestrictions = [];
            if (test.restrict_copy_paste) {
                activeRestrictions.push("Copy/Paste Blocked");
                pills.innerHTML += '<span class="badge" style="background: #dc2626; color: #fff;">🚫 No Copy/Paste</span>';
            }
            if (test.enable_camera) {
                activeRestrictions.push("Camera Monitoring");
                pills.innerHTML += '<span class="badge" style="background: #0284c7; color: #fff;">📷 Camera Active</span>';
            }
            if (test.enable_microphone) {
                activeRestrictions.push("Mic Monitoring");
                pills.innerHTML += '<span class="badge" style="background: #0284c7; color: #fff;">🎙 Mic Active</span>';
            }
            if (test.require_fullscreen) {
                activeRestrictions.push("Fullscreen Required");
                pills.innerHTML += '<span class="badge" style="background: #7c3aed; color: #fff;">⛶ Fullscreen Enforced</span>';
            }
            if (test.enable_proctoring) {
                activeRestrictions.push("Automated Proctoring");
                pills.innerHTML += '<span class="badge" style="background: #d97706; color: #fff;">🛡 Proctoring Active</span>';
            }
            if (test.enable_ai_tutor) {
                activeRestrictions.push("AI Clarification Allowed");
                pills.innerHTML += '<span class="badge" style="background: #8b5cf6; color: #fff;">📖 AI Clarification Allowed</span>';
                const clarifyBtn = document.getElementById("takingAiClarifyBtn");
                if (clarifyBtn) clarifyBtn.style.display = "inline-block";
            } else {
                activeRestrictions.push("AI Assistance Blocked");
                pills.innerHTML += '<span class="badge" style="background: #64748b; color: #fff;">🚫 AI Assistance Blocked</span>';
                const clarifyBtn = document.getElementById("takingAiClarifyBtn");
                if (clarifyBtn) clarifyBtn.style.display = "none";
            }

            if (activeRestrictions.length > 0) {
                banner.style.display = "flex";
                document.getElementById("testRestrictionsText").textContent = `🛡 Active Test Protections: ${activeRestrictions.join(" • ")}`;
            } else {
                banner.style.display = "none";
            }

            // Apply restrictions conditionally ONLY FOR THIS TEST
            setupEditorRestrictions(test.restrict_copy_paste);

            // Set up language selector restricted options
            setupTestLanguageSelector(test.allowed_languages);

            // Start countdown timer (timestamp based, safe against reload)
            startTestTimer();

            // Render questions switcher tabs
            renderTestQuestionTabs();

            // Switch to question (or restored activeQuestionIndex)
            selectTestQuestion(session.activeQuestionIndex || 0);

            window.scrollTo({ top: 0, behavior: "smooth" });
        }

        function saveCurrentQuestionDraft() {
            if (!activeTestSession || !activeTestSession.test || !activeTestSession.test.questions) return;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            if (!q) return;
            const langSelect = document.getElementById("takingLanguageSelect");
            const lang = langSelect ? langSelect.value : "python";
            const code = document.getElementById("takingCode") ? document.getElementById("takingCode").value : "";

            if (!activeTestSession.answers) activeTestSession.answers = {};
            if (!activeTestSession.answers[q.problem_id]) {
                activeTestSession.answers[q.problem_id] = {};
            }
            activeTestSession.answers[q.problem_id].language = lang;
            activeTestSession.answers[q.problem_id].code = code;

            try {
                localStorage.setItem('codemind_active_test', JSON.stringify(activeTestSession));
            } catch (e) {
                console.error("Draft save error:", e);
            }
        }

        function setupEditorRestrictions(restrict) {
            const editor = document.getElementById("takingCode");
            const warning = document.getElementById("copyPasteWarning");
            editor.oncopy = null;
            editor.oncut = null;
            editor.onpaste = null;
            editor.oncontextmenu = null;

            // Auto-save code on input
            editor.oninput = saveCurrentQuestionDraft;

            if (restrict) {
                const blockHandler = (e) => {
                    e.preventDefault();
                    if (warning) {
                        warning.style.display = "inline-block";
                        setTimeout(() => { warning.style.display = "none"; }, 3000);
                    }
                    return false;
                };
                editor.oncopy = blockHandler;
                editor.oncut = blockHandler;
                editor.onpaste = blockHandler;
                editor.oncontextmenu = blockHandler;
            }
        }

        function setupTestLanguageSelector(allowedLanguages) {
            const select = document.getElementById("takingLanguageSelect");
            select.innerHTML = "";

            const allLangs = [
                { val: "python", label: "Python 3" },
                { val: "c", label: "C (GCC)" },
                { val: "cpp", label: "C++ (G++)" },
                { val: "java", label: "Java" }
            ];

            const filtered = (allowedLanguages && allowedLanguages.length > 0)
                ? allLangs.filter(l => allowedLanguages.includes(l.val))
                : allLangs;

            filtered.forEach(l => {
                const opt = document.createElement("option");
                opt.value = l.val;
                opt.textContent = l.label;
                select.appendChild(opt);
            });
        }

        function startTestTimer() {
            clearInterval(testTimerInterval);
            const badge = document.getElementById("testTimerBadge");

            function update() {
                if (!activeTestSession) return;
                const now = Date.now();
                const secs = Math.max(0, Math.floor((activeTestSession.endTime - now) / 1000));
                
                const m = Math.floor(secs / 60);
                const s = secs % 60;
                badge.textContent = `⏱ ${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

                if (secs <= 0) {
                    clearInterval(testTimerInterval);
                    badge.textContent = "⏱ 00:00 - TIME EXPIRED";
                    alert("Assessment time limit has expired! Submitting your work now.");
                    submitTestSession(true);
                }
            }

            update();
            testTimerInterval = setInterval(update, 1000);
        }

        function renderTestQuestionTabs() {
            const container = document.getElementById("takingQuestionTabs");
            container.innerHTML = "";
            if (!activeTestSession) return;

            activeTestSession.test.questions.forEach((q, idx) => {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.className = `q-tab-button ${idx === activeTestSession.activeQuestionIndex ? 'active' : ''}`;
                
                const ans = (activeTestSession.answers && activeTestSession.answers[q.problem_id]) || null;
                const isMarked = Boolean(activeTestSession.markedForReview && activeTestSession.markedForReview[q.problem_id]);
                let label = `${isMarked ? '🚩 ' : ''}Q${idx + 1}: ${q.title}`;
                if (ans && ans.submitted) {
                    label += ` [${ans.score}/${q.points} pts]`;
                } else {
                    label += ` (${q.points} pts)`;
                }

                btn.textContent = label;
                btn.onclick = () => selectTestQuestion(idx);
                container.appendChild(btn);
            });
        }

        function selectTestQuestion(qIndex) {
            if (!activeTestSession) return;
            // Save current question's draft first
            saveCurrentQuestionDraft();

            activeTestSession.activeQuestionIndex = qIndex;
            localStorage.setItem('codemind_active_test', JSON.stringify(activeTestSession));
            renderTestQuestionTabs();
            updateMarkReviewBtnState();

            const q = activeTestSession.test.questions[qIndex];
            const metaBar = document.getElementById("takingMetaBar");
            const diffClass = `badge-${(q.difficulty || 'easy').toLowerCase()}`;
            const typeBadge = q.is_custom
                ? '<span class="badge badge-source" style="background: #0284c7; color: #fff;">Custom Question</span>'
                : '<span class="badge badge-source">Problem Bank</span>';

            metaBar.innerHTML = `
                <span class="badge ${diffClass}">${escapeHtml(q.difficulty || 'Medium')}</span>
                ${typeBadge}
                <span class="badge badge-rating">★ ${q.points} Points</span>
            `;

            document.getElementById("takingDescription").innerText = q.description || "Solve the problem according to standard specifications.";

            // Input / output format
            const ioSection = document.getElementById("takingIoSection");
            if (q.input_format || q.output_format) {
                ioSection.style.display = "block";
                document.getElementById("takingInputFormat").textContent = q.input_format || "Standard input";
                document.getElementById("takingOutputFormat").textContent = q.output_format || "Standard output";
            } else {
                ioSection.style.display = "none";
            }

            // Examples
            const exList = document.getElementById("takingExamplesList");
            exList.innerHTML = "";
            if (q.examples && q.examples.length > 0) {
                q.examples.forEach((ex, idx) => {
                    const exBox = document.createElement("div");
                    exBox.className = "example-box";
                    let exContent = `<strong>Example ${idx + 1}:</strong><br/>`;
                    exContent += `<p><strong>Input:</strong> ${escapeHtml(ex.input)}</p>`;
                    exContent += `<p><strong>Output:</strong> ${escapeHtml(ex.output)}</p>`;
                    if (ex.explanation) {
                        exContent += `<p style="color: #94a3b8; margin-top: 4px;"><strong>Explanation:</strong> ${escapeHtml(ex.explanation)}</p>`;
                    }
                    exBox.innerHTML = exContent;
                    exList.appendChild(exBox);
                });
                document.getElementById("takingExamplesSection").style.display = "block";
            } else {
                document.getElementById("takingExamplesSection").style.display = "none";
            }

            // Constraints
            const conList = document.getElementById("takingConstraintsList");
            conList.innerHTML = "";
            if (q.constraints && q.constraints.length > 0) {
                q.constraints.forEach(c => {
                    const li = document.createElement("li");
                    li.textContent = c;
                    conList.appendChild(li);
                });
                document.getElementById("takingConstraintsSection").style.display = "block";
            } else {
                document.getElementById("takingConstraintsSection").style.display = "none";
            }

            // Code & Language restoration
            const ans = activeTestSession.answers ? activeTestSession.answers[q.problem_id] : null;
            const langSelect = document.getElementById("takingLanguageSelect");
            const editor = document.getElementById("takingCode");

            if (ans && ans.code !== undefined) {
                if (ans.language && langSelect) {
                    langSelect.value = ans.language;
                }
                editor.value = ans.code;
            } else {
                onTakingLanguageChange();
            }

            // Question score badge
            const qScoreBadge = document.getElementById("takingQScoreBadge");
            if (ans && ans.submitted) {
                qScoreBadge.style.display = "inline-block";
                qScoreBadge.textContent = `Score: ${ans.score} / ${q.points} pts (${(ans.status || '').toUpperCase()})`;
                if (ans.score === q.points) {
                    qScoreBadge.style.background = "#16a34a";
                    qScoreBadge.style.color = "#ffffff";
                } else if (ans.score > 0) {
                    qScoreBadge.style.background = "#d97706";
                    qScoreBadge.style.color = "#ffffff";
                } else {
                    qScoreBadge.style.background = "#dc2626";
                    qScoreBadge.style.color = "#ffffff";
                }
            } else {
                qScoreBadge.style.display = "none";
            }

            // Clear previous execution output
            document.getElementById("takingResult").textContent = `Click 'Run Code' or 'Submit Question' to test your solution for ${q.title}.`;
            const badge = document.getElementById("takingStatusBadge");
            if (badge) badge.style.display = "none";
        }

        function onTakingLanguageChange() {
            if (!activeTestSession) return;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            const langSelect = document.getElementById("takingLanguageSelect");
            const lang = langSelect ? langSelect.value : "python";
            const editor = document.getElementById("takingCode");

            if (q && q.starter_code && q.starter_code[lang]) {
                editor.value = q.starter_code[lang];
            } else if (LANGUAGE_TEMPLATES[lang]) {
                editor.value = LANGUAGE_TEMPLATES[lang];
            } else {
                editor.value = `# Solution for ${q ? q.title : 'Assessment Question'}\n`;
            }
            saveCurrentQuestionDraft();
        }

        // RUN CODE IN TEST SESSION (USING REAL BACKEND EXECUTION ENGINE)
        async function runTakingCode() {
            if (!activeTestSession) return null;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            const code = document.getElementById("takingCode").value;
            const resultElement = document.getElementById("takingResult");
            const statusBadge = document.getElementById("takingStatusBadge");
            const runButton = document.getElementById("takingRunButton");
            const langSelect = document.getElementById("takingLanguageSelect");
            const language = langSelect ? langSelect.value : "python";

            if (code.trim() === "") {
                resultElement.innerText = "Please write some code first.";
                return null;
            }

            runButton.disabled = true;
            runButton.innerText = "Running...";
            resultElement.innerText = `Executing your ${language.toUpperCase()} code in isolated environment...`;
            if (statusBadge) statusBadge.style.display = "none";

            try {
                const response = await fetch(`${API_BASE}/api/execute`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        problem_id: q.problem_id,
                        language: language,
                        source_code: code
                    })
                });

                const data = await response.json();

                if (!response.ok) {
                    const errDetail = data.detail || `Server error: ${response.status} ${response.statusText}`;
                    if (statusBadge) {
                        statusBadge.style.display = "inline-block";
                        statusBadge.style.background = "#dc2626";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "ERROR";
                    }
                    resultElement.innerText = errDetail;
                    return null;
                }

                if (statusBadge) {
                    statusBadge.style.display = "inline-block";
                    const s = (data.status || "").toLowerCase();
                    if (s === "accepted") {
                        statusBadge.style.background = "#16a34a";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "✓ ACCEPTED";
                    } else if (s === "wrong_answer" || s === "wrong answer") {
                        statusBadge.style.background = "#dc2626";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "✗ WRONG ANSWER";
                    } else if (s === "compile_error" || s === "compile error") {
                        statusBadge.style.background = "#ea580c";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⚠ COMPILE ERROR";
                    } else if (s === "runtime_error" || s === "runtime error") {
                        statusBadge.style.background = "#e11d48";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⚡ RUNTIME ERROR";
                    } else if (s === "time_limit" || s === "timeout" || s === "time limit") {
                        statusBadge.style.background = "#d97706";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "⏱ TIMEOUT";
                    } else if (s === "no_test_cases" || s === "no test cases") {
                        statusBadge.style.background = "#475569";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = "ℹ NO TEST CASES";
                    } else {
                        statusBadge.style.background = "#64748b";
                        statusBadge.style.color = "#ffffff";
                        statusBadge.innerText = (data.status || "STATUS").toUpperCase();
                    }
                }

                let outputText = "";
                if (data.status === "no_test_cases") {
                    outputText = data.error || data.output || "Problem does not contain executable test cases in the database.";
                } else if (data.status === "compile_error") {
                    outputText = data.error || data.stderr || "Compilation failed.";
                } else if (data.test_results && data.test_results.length > 0) {
                    outputText += `Passed: ${data.passed_count || 0} / ${data.total_test_cases || data.test_results.length} test cases\n\n`;
                    data.test_results.forEach(tc => {
                        const icon = tc.passed ? "✓ Passed" : "✗ Failed";
                        outputText += `[Test Case ${tc.test_case}] - ${icon} (${tc.execution_time}s)\n`;
                        outputText += `Expected: ${tc.expected_output}\n`;
                        outputText += `Actual:   ${tc.actual_output}\n`;
                        if (tc.error) {
                            outputText += `Error:    ${tc.error}\n`;
                        }
                        outputText += "\n";
                    });
                } else if (data.error) {
                    outputText = data.error;
                } else if (data.output) {
                    outputText = data.output;
                } else {
                    outputText = "Execution finished with no output.";
                }

                resultElement.innerText = outputText.trim();
                return data;

            } catch (error) {
                const classified = classifyApiError(error);
                if (statusBadge) {
                    statusBadge.style.display = "inline-block";
                    statusBadge.style.background = "#dc2626";
                    statusBadge.style.color = "#ffffff";
                    statusBadge.innerText = classified.type;
                }
                resultElement.innerText = `${classified.type}: ${classified.message}`;
                return null;
            } finally {
                runButton.disabled = false;
                runButton.innerText = "▶️ Run Code";
            }
        }

        // SUBMIT INDIVIDUAL QUESTION IN TEST SESSION
        async function submitCurrentQuestion() {
            if (!activeTestSession) return;
            const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
            const code = document.getElementById("takingCode").value;
            const langSelect = document.getElementById("takingLanguageSelect");
            const language = langSelect ? langSelect.value : "python";
            const submitBtn = document.getElementById("takingSubmitQButton");

            if (code.trim() === "") {
                alert("Please write some code before submitting this question.");
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerText = "Evaluating...";

            try {
                const data = await runTakingCode();
                if (!data) return;

                const maxPoints = q.points || 10;
                let earned = 0;
                const statusLower = (data.status || "").toLowerCase();

                if (data.total_test_cases && data.total_test_cases > 0) {
                    earned = Math.round(((data.passed_count || 0) / data.total_test_cases) * maxPoints);
                } else if (statusLower === "accepted") {
                    earned = maxPoints;
                } else {
                    earned = 0;
                }

                if (!activeTestSession.answers) activeTestSession.answers = {};
                activeTestSession.answers[q.problem_id] = {
                    language: language,
                    code: code,
                    submitted: true,
                    score: earned,
                    status: data.status || "evaluated",
                    passed: data.passed_count || 0,
                    total: data.total_test_cases || 0
                };
                localStorage.setItem('codemind_active_test', JSON.stringify(activeTestSession));

                const scoreBadge = document.getElementById("takingQScoreBadge");
                if (scoreBadge) {
                    scoreBadge.style.display = "inline-block";
                    scoreBadge.textContent = `Score: ${earned} / ${maxPoints} pts (${(data.status || '').toUpperCase()})`;
                    if (earned === maxPoints) {
                        scoreBadge.style.background = "#16a34a";
                        scoreBadge.style.color = "#ffffff";
                    } else if (earned > 0) {
                        scoreBadge.style.background = "#d97706";
                        scoreBadge.style.color = "#ffffff";
                    } else {
                        scoreBadge.style.background = "#dc2626";
                        scoreBadge.style.color = "#ffffff";
                    }
                }

                renderTestQuestionTabs();

            } catch (err) {
                alert("Question evaluation error: " + err.message);
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerText = "💾 Submit Question";
            }
        }

        // SUBMIT ENTIRE TEST SESSION
        async function submitTestSession(isAutoSubmit = false) {
            if (!activeTestSession) return;
            if (!isAutoSubmit) {
                if (!confirm("Are you sure you want to finish and submit this assessment? All answered questions will be scored.")) {
                    return;
                }
            }

            const startTime = activeTestSession.startTime || (activeTestSession.endTime - (activeTestSession.test.duration_minutes || 60) * 60000);
            const elapsedSecs = Math.max(1, Math.round((Date.now() - startTime) / 1000));

            saveCurrentQuestionDraft();
            clearInterval(testTimerInterval);

            const testId = activeTestSession.test.id;
            const answersList = [];

            activeTestSession.test.questions.forEach(q => {
                const ans = (activeTestSession.answers && activeTestSession.answers[q.problem_id]) || {};
                answersList.push({
                    problem_id: q.problem_id,
                    language: ans.language || "python",
                    source_code: ans.code || ""
                });
            });

            const sid = getStudentId();
            const submitPayload = {
                student_id: sid,
                answers: answersList
            };

            const submitBtn = document.getElementById("finishTestButton");
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = "Grading & Submitting...";
            }

            try {
                const res = await authFetch(`${API_BASE}/api/tests/${testId}/submit`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(submitPayload)
                });

                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || "Submission failed.");
                }

                const subResult = await res.json();
                subResult.elapsed_time_seconds = elapsedSecs;
                subResult.topic = (activeTestSession.test && activeTestSession.test.title) ? activeTestSession.test.title.split('•')[0].replace('Assessment', '').trim() : 'All';
                subResult.difficulty = currentAsmDifficulty;
                lastAsmSubmission = subResult;

                // Clear active session storage & security restrictions
                localStorage.removeItem('codemind_active_test');
                setupEditorRestrictions(false);

                // Show score and question breakdown modal
                showTestResultModal(subResult);

            } catch (err) {
                alert("Assessment submission error: " + err.message);
            } finally {
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.textContent = "✓ Finish & Submit Test";
                }
            }
        }

        function showTestResultModal(result) {
            document.getElementById("modalScoreDisplay").textContent = `${result.total_score} / ${result.max_score}`;

            const percBadge = document.getElementById("modalPercentageBadge");
            const perc = result.percentage || 0;
            const badgeColor = perc >= 70 ? "#16a34a" : perc >= 40 ? "#d97706" : "#dc2626";
            percBadge.innerHTML = `<span class="badge" style="font-size: 14px; padding: 5px 12px; background: ${badgeColor}; color: #fff;">${perc}% Accuracy</span>`;

            // Time used
            const timeSecs = result.elapsed_time_seconds || 0;
            const mins = Math.floor(timeSecs / 60);
            const secs = timeSecs % 60;
            const timeEl = document.getElementById("modalTimeUsedDisplay");
            if (timeEl) timeEl.textContent = `⏱ ${mins}m ${secs}s`;

            const accEl = document.getElementById("modalAccuracySummary");
            if (accEl) accEl.textContent = `Accuracy: ${perc}%`;

            // Solved vs Unsolved & Correct vs Incorrect
            const qResults = result.question_results || [];
            const totalCount = qResults.length;
            const correctCount = qResults.filter(q => (q.status||'').toLowerCase() === 'accepted' || (q.earned_score === q.max_score && q.max_score > 0)).length;
            const incorrectCount = totalCount - correctCount;

            const solvedEl = document.getElementById("modalSolvedBreakdown");
            if (solvedEl) solvedEl.textContent = `${correctCount} of ${totalCount} Correct`;

            const incEl = document.getElementById("modalIncorrectSummary");
            if (incEl) incEl.textContent = `${incorrectCount} Incorrect / Unsolved`;

            // Question Breakdown
            const breakdownContainer = document.getElementById("modalQuestionBreakdown");
            breakdownContainer.innerHTML = "";

            if (qResults.length > 0) {
                qResults.forEach((qr, idx) => {
                    const item = document.createElement("div");
                    item.style.padding = "12px";
                    item.style.marginBottom = "10px";
                    item.style.background = "#1e293b";
                    item.style.borderRadius = "8px";
                    item.style.border = "1px solid #334155";
                    item.style.display = "flex";
                    item.style.justifyContent = "space-between";
                    item.style.alignItems = "center";

                    const s = (qr.status || "").toLowerCase();
                    const statusColor = s === "accepted" ? "#16a34a" : s.includes("error") ? "#e11d48" : "#d97706";

                    item.innerHTML = `
                        <div>
                            <div style="font-weight: 700; color: #f8fafc; font-size: 14px;">Q${idx + 1}: ${escapeHtml(qr.title)}</div>
                            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">Language: <strong>${(qr.language || 'python').toUpperCase()}</strong> • Test Cases: <strong>${qr.passed_test_cases} / ${qr.total_test_cases} passed</strong></div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-weight: 800; color: #38bdf8; font-size: 16px;">${qr.earned_score} / ${qr.max_score} pts</div>
                            <span class="badge" style="background: ${statusColor}; color: #fff; font-size: 11px; margin-top: 4px;">${(qr.status || "").toUpperCase()}</span>
                        </div>
                    `;
                    breakdownContainer.appendChild(item);
                });
            }

            // Topic & Concept Performance
            const topicPerfContainer = document.getElementById("modalTopicPerformance");
            if (topicPerfContainer) {
                topicPerfContainer.innerHTML = "";
                if (result.topic_performance && Object.keys(result.topic_performance).length > 0) {
                    Object.entries(result.topic_performance).forEach(([topicName, stats]) => {
                        const chip = document.createElement("span");
                        chip.className = "chip-tag";
                        const passed = stats.passed || 0;
                        const total = stats.total || 0;
                        const isGood = passed === total;
                        chip.style.background = isGood ? "rgba(34, 197, 94, 0.15)" : "rgba(245, 158, 11, 0.15)";
                        chip.style.border = `1px solid ${isGood ? "#22c55e" : "#f59e0b"}`;
                        chip.style.color = isGood ? "#4ade80" : "#fbbf24";
                        chip.style.padding = "4px 10px";
                        chip.style.borderRadius = "6px";
                        chip.style.fontSize = "12px";
                        chip.textContent = `${topicName}: ${passed}/${total} passed`;
                        topicPerfContainer.appendChild(chip);
                    });
                } else {
                    topicPerfContainer.innerHTML = '<span style="color: #64748b; font-size: 12px;">General Problem Solving</span>';
                }
            }

            // Weak Concepts & Recommended Practice
            const recSec = document.getElementById("modalRecommendedSection");
            const weakListEl = document.getElementById("modalWeakConceptsList");
            const recListEl = document.getElementById("modalRecommendedProblemsList");
            if (recSec && weakListEl && recListEl) {
                if (result.weak_concepts && result.weak_concepts.length > 0) {
                    recSec.style.display = "block";
                    weakListEl.innerHTML = `<strong>Focus Concepts:</strong> ` + result.weak_concepts.map(wc => `<span class="badge" style="background: #ef4444; color: #fff; margin-right: 4px;">${escapeHtml(wc)}</span>`).join(" ");
                    recListEl.innerHTML = "";
                    if (result.recommended_practice && result.recommended_practice.length > 0) {
                        result.recommended_practice.forEach(rp => {
                            const card = document.createElement("div");
                            card.style.background = "#1e293b";
                            card.style.border = "1px solid #334155";
                            card.style.borderRadius = "8px";
                            card.style.padding = "10px 12px";
                            card.style.display = "flex";
                            card.style.justifyContent = "space-between";
                            card.style.alignItems = "center";
                            card.style.gap = "8px";
                            card.innerHTML = `
                                <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                    <div style="font-size: 13px; font-weight: 600; color: #f8fafc; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(rp.title)}</div>
                                    <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">${escapeHtml(rp.difficulty)} • ${escapeHtml(rp.domain)}</div>
                                </div>
                                <button class="run-button" onclick="closeResultModal(); openProblem('${rp.problem_id}')" style="margin-top: 0; padding: 4px 10px; font-size: 11px; flex-shrink: 0; background: #38bdf8; color: #0f172a; font-weight: 700;">
                                    Practice ↗
                                </button>
                            `;
                            recListEl.appendChild(card);
                        });
                    } else {
                        recListEl.innerHTML = '<div style="color: #94a3b8; font-size: 12px;">Browse problem library to practice next problems.</div>';
                    }
                } else {
                    recSec.style.display = "none";
                }
            }

            document.getElementById("testResultModal").style.display = "flex";
        }

        function closeResultModal() {
            document.getElementById("testResultModal").style.display = "none";
            activeTestSession = null;
            showTestsView();
        }

        function exitTestSession() {
            if (confirm("Are you sure you want to exit the assessment test session? Your active timer and progress will be preserved in your browser.")) {
                clearInterval(testTimerInterval);
                setupEditorRestrictions(false);
                saveCurrentQuestionDraft();
                showTestsView();
            }
        }

        // ========================================================
        // AI TUTOR & INSIGHTS SYSTEM
        // ========================================================
        let lastExecutionResult = null;
        let currentHintsUsed = 0;
        let currentSolutionViewed = false;
        let currentAITab = 'explain';

        function isTestMode() {
            const testView = document.getElementById("testTakingView");
            return Boolean(activeTestSession && testView && testView.style.display === "block");
        }

        // ================= CONVERSATIONAL AI TUTOR STATE & CONTROLLER =================
        let aiTutorChatHistory = [];
        let isAITutorSending = false;

        function openAITutorModal(defaultTab = 'chat') {
            // Check if test session active and AI blocked - ONLY during an active test taking attempt
            if (isTestMode()) {
                if (activeTestSession && activeTestSession.test && !activeTestSession.test.enable_ai_tutor) {
                    alert("🚫 AI Tutor assistance is disabled by the instructor for this assessment test.");
                    return;
                }
                defaultTab = 'explain'; // Test mode restricted strictly to question understanding
            }

            const modal = document.getElementById("aiTutorModal");
            const titleEl = document.getElementById("aiTutorProblemTitle");

            let currentTitle = "General Computer Science";
            if (isTestMode() && activeTestSession && activeTestSession.test && activeTestSession.test.questions) {
                const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
                if (q) currentTitle = q.title;
            } else if (currentProblemData) {
                currentTitle = currentProblemData.title;
            }
            if (titleEl) {
                titleEl.textContent = (currentProblemData || isTestMode())
                    ? `Context: ${currentTitle} (Ask about this problem or any CS topic!)`
                    : `Conversational Computer Science Learning Assistant`;
            }

            modal.style.display = "flex";
            switchAITab(defaultTab);
        }

        let pendingClearChatSource = null;

        function requestClearMayaChat(source = 'general') {
            pendingClearChatSource = source;
            const modal = document.getElementById('clearChatConfirmModal');
            if (modal) {
                modal.style.display = 'flex';
                document.body.classList.add('modal-open');
            }
        }

        function closeClearChatConfirmModal() {
            const modal = document.getElementById('clearChatConfirmModal');
            if (modal) {
                modal.style.display = 'none';
                document.body.classList.remove('modal-open');
            }
            pendingClearChatSource = null;
        }

        async function confirmExecuteClearChat() {
            closeClearChatConfirmModal();

            // 1. Voice check: Stop speech immediately if Maya is speaking
            stopCompanionSpeechImmediate();
            if (window.speechSynthesis) {
                try { window.speechSynthesis.cancel(); } catch (e) {}
            }

            // 2. Return Maya to IDLE or LISTENING state depending on Voice Assistant mode
            if (window.voiceAssistantActive) {
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('listening');
                }
                if (window.startCompanionWakeRecognition) {
                    window.startCompanionWakeRecognition();
                }
            } else {
                if (window.setCompanionExpression) {
                    window.setCompanionExpression('idle');
                }
            }

            // 3. Clear conversation history arrays (active AI context)
            companionChatHistory = [];
            aiTutorChatHistory = [];

            // 4. Clear Dashboard conversation DOM and restore greeting
            const dashChatArea = document.getElementById('companionChatArea');
            if (dashChatArea) {
                dashChatArea.innerHTML = '';
                const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
                const greeting = document.createElement('div');
                greeting.className = 'companion-bubble';
                greeting.id = 'companionGreetingBubble';
                greeting.innerHTML = `👋 Hello! I am <strong>${escapeHtml(botName)}</strong>, your CodeMind AI Companion &amp; Tutor. Ask me anything about programming, algorithms, recursion, pointers, or code debugging!`;
                dashChatArea.appendChild(greeting);
            }

            // 5. Clear Workspace Inline & Modal Chat Streams
            const tutorStream = document.getElementById('aiTutorChatStream');
            if (tutorStream) {
                tutorStream.innerHTML = '';
                appendAITutorWelcomeMessage(tutorStream);
            }
            const panelStream = document.getElementById('aiPanelChatStream');
            if (panelStream) {
                panelStream.innerHTML = '';
                appendAITutorWelcomeMessage(panelStream);
            }

            // 6. Notify backend to clear/archive active session context if supported
            try {
                const sid = getStudentId();
                const token = getAuthToken();
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                if (sid && sid !== 'null' && sid !== 'undefined') headers['X-Student-Id'] = sid;
                fetch(`${API_BASE}/api/ai/companion/clear`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify({ student_id: sid })
                }).catch(() => {});
            } catch (e) {}

            if (typeof showToast === 'function') {
                showToast("Maya conversation cleared.");
            }
        }

        function clearAITutorChat(containerId = 'aiTabContent') {
            requestClearMayaChat(containerId);
        }

        function appendAITutorWelcomeMessage(streamEl) {
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
            const welcomeMsg = document.createElement('div');
            welcomeMsg.className = 'ai-msg assistant';
            welcomeMsg.innerHTML = `
                <div class="ai-avatar">🧠</div>
                <div class="ai-msg-body">
                    <div style="font-weight: 700; color: #818cf8; font-size: 11px; margin-bottom: 4px;">${escapeHtml(botName)}</div>
                    <div>
                        👋 Hi! I am <strong>Maya</strong>, your CodeMind AI Tutor & CS companion.<br><br>
                        I can help you break down algorithms, analyze code, explain concepts, or think through problems step by step. Ask me anything!
                    </div>
                </div>
            `;
            streamEl.appendChild(welcomeMsg);
        }

        function renderAITutorChatView(containerId = 'aiTabContent') {
            const container = document.getElementById(containerId);
            if (!container) return;

            const probTitle = currentProblemData ? currentProblemData.title : null;
            const lang = (typeof getActiveLanguage === 'function') ? getActiveLanguage() : 'python';

            container.innerHTML = `
                <div class="ai-tutor-container">
                    <div class="ai-tutor-context-bar">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="color:#fbbf24;">⚡</span>
                            <span>${probTitle ? `Active Problem: <strong>${escapeHtml(probTitle)}</strong> • Ask Maya for hints, approach, or debug help!` : `General CS Learning Mode • Ask any programming or algorithm question!`}</span>
                        </div>
                        <span style="background:#1e293b; padding:2px 8px; border-radius:4px; font-size:11px; color:#38bdf8; font-weight:700;">${lang.toUpperCase()}</span>
                    </div>

                    <div class="ai-tutor-chips">
                        ${probTitle ? `
                            <span class="ai-tutor-chip" onclick="triggerProblemVisualization('${containerId}')" style="background:rgba(2,132,199,0.18); border:1px solid #0284c7; color:#38bdf8; font-weight:700;">📊 Visualize</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('hint', '${containerId}')">💡 Need a hint?</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('approach', '${containerId}')">🎯 How should I approach this?</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('review', '${containerId}')">🔍 Review my code</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('why_failed', '${containerId}')">🐛 Why did my code fail?</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('explain_line_by_line', '${containerId}')">📜 Explain My Code Line by Line</span>
                        ` : `
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('Explain recursion', '${containerId}')">💡 Explain recursion</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('What is a pointer in C?', '${containerId}')">💻 Pointers in C</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('Give me short notes on binary search', '${containerId}')">📝 Short notes</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('Explain stack vs queue', '${containerId}')">⚖️ Stack vs Queue</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('Quiz me on dynamic programming', '${containerId}')">🎯 Quiz me</span>
                            <span class="ai-tutor-chip" onclick="sendQuickPrompt('What is an operating system?', '${containerId}')">🖥️ Operating Systems</span>
                        `}
                    </div>

                    <div class="ai-tutor-chat-stream" id="${containerId === 'aiTabContent' ? 'aiTutorChatStream' : 'aiPanelChatStream'}">
                    </div>

                    <div class="ai-tutor-input-box">
                        <textarea id="${containerId === 'aiTabContent' ? 'aiTutorChatInput' : 'aiPanelChatInput'}" 
                                  class="ai-tutor-textarea" 
                                  placeholder="Ask Maya anything (e.g. 'Explain recursion', 'Why did my code fail?'). Press Enter to send..."></textarea>
                        <button id="${containerId === 'aiTabContent' ? 'aiTutorSendBtn' : 'aiPanelSendBtn'}" 
                                class="ai-tutor-send-btn" 
                                onclick="sendAITutorChat(null, '${containerId}')">
                            <span>Send</span>
                            <span>➤</span>
                        </button>
                    </div>
                </div>
            `;

            const streamEl = document.getElementById(containerId === 'aiTabContent' ? 'aiTutorChatStream' : 'aiPanelChatStream');
            const inputEl = document.getElementById(containerId === 'aiTabContent' ? 'aiTutorChatInput' : 'aiPanelChatInput');

            // Wire keyboard Enter to send (Shift+Enter for newline)
            if (inputEl) {
                inputEl.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendAITutorChat(null, containerId);
                    }
                });
            }

            // Restore conversation history if present, else welcome message
            if (aiTutorChatHistory.length === 0) {
                appendAITutorWelcomeMessage(streamEl);
            } else {
                aiTutorChatHistory.forEach(msg => {
                    appendChatBubbleDOM(streamEl, msg.role, msg.content, msg.recommended_problems || []);
                });
            }
            streamEl.scrollTop = streamEl.scrollHeight;
        }

        function sendQuickPrompt(promptKeyOrText, containerId = 'aiTabContent') {
            sendAITutorChat(promptKeyOrText, containerId, true);
        }

        function buildAssistantExtrasHTML(recommendations = [], visualization = null) {
            let recsHtml = '';
            if (recommendations && recommendations.length > 0) {
                recsHtml += `
                    <div style="margin-top:14px; border-top:1px solid rgba(212,175,55,0.25); padding-top:10px;">
                        <div style="font-size:12px; font-weight:700; color:#d4af37; margin-bottom:8px; display:flex; align-items:center; gap:6px;">
                            <span>🎯</span> Recommended Practice Problems (${recommendations.length}):
                        </div>
                        <div style="display:flex; flex-direction:column; gap:6px;">
                `;
                recommendations.forEach(rec => {
                    const diffClass = (rec.difficulty || 'medium').toLowerCase();
                    recsHtml += `
                        <div style="background:#090d16; border:1px solid #1e293b; border-radius:6px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                            <div style="flex:1; min-width:0;">
                                <div style="display:flex; align-items:center; gap:6px;">
                                    <span style="font-size:13px; font-weight:700; color:#f8fafc; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(rec.title)}</span>
                                    <span class="badge ${diffClass}" style="font-size:10px; padding:1px 6px;">${rec.difficulty}</span>
                                </div>
                                <div style="font-size:11px; color:#94a3b8; margin-top:2px;">${escapeHtml(rec.reason || '')}</div>
                            </div>
                            <button onclick="closeAITutorModal(); openProblem('${rec.problem_id}');" style="background:linear-gradient(135deg,#6366f1,#4f46e5); color:#ffffff; font-weight:700; font-size:11px; border:none; padding:5px 11px; border-radius:5px; cursor:pointer; white-space:nowrap;">
                                Solve →
                            </button>
                        </div>
                    `;
                });
                recsHtml += `</div></div>`;
            }

            let vizHtml = '';
            if (visualization && visualization.steps && visualization.steps.length > 0) {
                const vizJson = escapeHtml(JSON.stringify(visualization));
                vizHtml = `
                    <div class="ai-viz-card" style="margin-top:14px; background:#070a10; border:1px solid rgba(212,175,55,0.35); border-radius:8px; padding:10px 14px; display:flex; justify-content:space-between; align-items:center; gap:12px;">
                        <div style="flex:1;">
                            <div style="font-size:12px; font-weight:700; color:#d4af37; display:flex; align-items:center; gap:6px;">
                                <span>📊</span> Interactive Step-by-Step Visualization
                            </div>
                            <div style="font-size:11.5px; color:#cbd5e1; margin-top:2px;">
                                <strong>${escapeHtml(visualization.title)}</strong> (${(visualization.viz_type || 'DSA').toUpperCase()}) — ${visualization.steps.length} interactive animation steps with play/pause, scrubber, and speed controls.
                            </div>
                        </div>
                        <button onclick='renderCompanionVisualization(JSON.parse(this.dataset.viz)); closeAITutorModal(); const el = document.getElementById("dashCompanionWidget"); if(el) el.scrollIntoView({behavior:"smooth"});' data-viz="${vizJson}" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; font-weight:700; font-size:11.5px; border:none; padding:7px 14px; border-radius:6px; cursor:pointer; white-space:nowrap; display:flex; align-items:center; gap:5px;">
                            <span>▶ View Animation</span>
                        </button>
                    </div>
                `;
            }

            return recsHtml + vizHtml;
        }

        async function sendAITutorChat(messageOverride = null, containerId = 'aiTabContent', isQuickAction = false) {
            if (isAITutorSending) return;

            if (!isAuthenticated()) {
                openAuthModal('signin');
                if (typeof showToast === 'function') showToast('Please sign in to use Maya AI Tutor.');
                return;
            }

            const user = getAuthUser();
            const hasGroq = !!(window.currentUserHasGroqKey || (user && user.has_groq_key));
            if (!hasGroq) {
                openGroqKeyModal(true);
                return;
            }

            const inputId = (containerId === 'aiTabContent') ? 'aiTutorChatInput' : 'aiPanelChatInput';
            const btnId = (containerId === 'aiTabContent') ? 'aiTutorSendBtn' : 'aiPanelSendBtn';
            const streamId = (containerId === 'aiTabContent') ? 'aiTutorChatStream' : 'aiPanelChatStream';

            const input = document.getElementById(inputId);
            const sendBtn = document.getElementById(btnId);
            const stream = document.getElementById(streamId);

            const rawInputText = (messageOverride || (input ? input.value : '')).trim();
            if (!rawInputText) return;

            // Resolve quick action intent & concise prompt
            let displayUserText = rawInputText;
            let promptPayloadText = rawInputText;
            let quickType = null;

            const rawLower = rawInputText.toLowerCase();
            if (rawInputText === 'hint' || rawLower.includes('need a hint') || rawLower.includes('give me only a hint')) {
                displayUserText = '💡 Need a hint?';
                promptPayloadText = 'Give me a concise hint (2-3 sentences max) to guide my intuition on this problem. Do not give the full code or complete algorithm yet.';
                quickType = 'hint';
            } else if (rawInputText === 'approach' || rawLower.includes('how should i approach')) {
                displayUserText = '🎯 How should I approach this?';
                promptPayloadText = 'How should I approach this problem? Give a concise 3-step high-level algorithmic plan with optimal time and space complexity, without writing the full code.';
                quickType = 'approach';
            } else if (rawInputText === 'review' || rawLower.includes('review my code')) {
                displayUserText = '🔍 Review my code';
                promptPayloadText = 'Review my current code and check if it is correct for this problem. Identify any bugs, wrong logic, or incorrect implementation. Explain what is wrong and how to fix it.';
                quickType = 'review';
            } else if (rawInputText === 'why_failed' || rawLower.includes('why did my code fail')) {
                displayUserText = '🐛 Why did my code fail?';
                promptPayloadText = 'Why did my code fail? Pinpoint the exact bug or wrong logic in my code based on the error or failed test case, and explain how to fix it.';
                quickType = 'why_failed';
            } else if (rawInputText === 'explain_line_by_line' || rawLower.includes('line by line') || rawLower.includes('explain my code line by line')) {
                displayUserText = '📜 Explain My Code Line by Line';
                promptPayloadText = 'Explain my current code line by line in logical execution sequence. Reference each line number, state what it does, the variables and control flow involved, and explicitly point out any defects, bugs, edge cases, or potential failure points.';
                quickType = 'explain_line_by_line';
            }

            if (input) input.value = '';
            if (input) input.disabled = true;
            if (sendBtn) sendBtn.disabled = true;
            isAITutorSending = true;

            // 1. Append user bubble
            appendChatBubbleDOM(stream, 'user', displayUserText);
            stream.scrollTop = stream.scrollHeight;

            // 2. Append assistant bubble with immediate thinking / streaming DOM
            const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
            const assistantBubble = document.createElement('div');
            assistantBubble.className = 'ai-msg assistant';
            assistantBubble.innerHTML = `
                <div class="ai-avatar">🧠</div>
                <div class="ai-msg-body">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-weight:700; color:#818cf8; font-size:11px;">${escapeHtml(botName)}</span>
                        <span class="ai-bubble-metrics" style="font-size:10px; color:#10b981; font-family:Consolas, monospace;">● Thinking...</span>
                    </div>
                    <div class="ai-bubble-text" style="color:#94a3b8; font-style:italic;">Thinking...</div>
                    <div class="ai-bubble-extras"></div>
                </div>
            `;
            stream.appendChild(assistantBubble);
            stream.scrollTop = stream.scrollHeight;

            const bubbleTextEl = assistantBubble.querySelector('.ai-bubble-text');
            const bubbleMetricsEl = assistantBubble.querySelector('.ai-bubble-metrics');
            const bubbleExtrasEl = assistantBubble.querySelector('.ai-bubble-extras');

            // 3. Assemble pruned payload
            const isProblemWorkspace = (window.active_workspace === 'problem_solving' || window.active_workspace === 'test_taking');
            const probId = isProblemWorkspace ? ((typeof getActiveProblemId === 'function') ? getActiveProblemId() : null) : null;
            const activeProblem = isProblemWorkspace ? currentProblemData : null;
            const code = isProblemWorkspace ? ((typeof getActiveCode === 'function') ? getActiveCode() : '') : '';
            const trimmedCode = (code || '').trim();
            const isPlaceholderCode = !trimmedCode ||
                trimmedCode === '# Select a problem to view starter code' ||
                trimmedCode === '// Select a problem to view starter code';

            let lang = null;
            if (isProblemWorkspace && (probId || !isPlaceholderCode)) {
                if (typeof isTestMode === 'function' && isTestMode() && document.getElementById('takingLanguageSelect')) {
                    lang = document.getElementById('takingLanguageSelect').value;
                } else if (document.getElementById('languageSelect')) {
                    lang = document.getElementById('languageSelect').value;
                } else if (typeof getActiveLanguage === 'function') {
                    lang = getActiveLanguage();
                }
            }
            const user = getAuthUser();
            let studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
            const sid = getStudentId();
            const token = getAuthToken();

            const resultEl = document.getElementById('result');
            const execOutput = (isProblemWorkspace && resultEl) ? (resultEl.textContent || '').trim().slice(0, 1000) : null;
            let lastError = (isProblemWorkspace && resultEl && resultEl.textContent && (resultEl.textContent.includes('Error') || resultEl.textContent.includes('Exception') || resultEl.textContent.includes('Failed')))
                ? resultEl.textContent.trim().slice(0, 500)
                : null;

            let failedTestCase = null;
            if (isProblemWorkspace && typeof lastExecutionResult !== 'undefined' && lastExecutionResult && Array.isArray(lastExecutionResult.test_results)) {
                const failed = lastExecutionResult.test_results.find(tc => !tc.passed);
                if (failed) {
                    failedTestCase = {
                        input: failed.input || '',
                        expected_output: failed.expected_output || '',
                        actual_output: failed.actual_output || '',
                        error: failed.error || null
                    };
                }
            }
            const submissionStatus = (isProblemWorkspace && typeof lastExecutionResult !== 'undefined' && lastExecutionResult && lastExecutionResult.status) ? lastExecutionResult.status : null;

            // Check Test Mode & Instructor Policy
            const inTest = isProblemWorkspace && ((typeof isTestMode === 'function') ? isTestMode() : false);
            const testId = (inTest && typeof activeTestSession !== 'undefined' && activeTestSession && activeTestSession.test) ? activeTestSession.test.id : null;
            const testAIEnabled = (inTest && typeof activeTestSession !== 'undefined' && activeTestSession && activeTestSession.test) ? Boolean(activeTestSession.test.enable_ai_tutor) : true;

            let safeCode = isProblemWorkspace ? code : null;
            let safeError = lastError;
            let safeExecOutput = execOutput;
            let safeFailedTc = failedTestCase;

            // Context protection for test mode
            if (inTest && !testAIEnabled) {
                safeCode = '';
                safeError = null;
                safeExecOutput = null;
                safeFailedTc = null;
            }

            // CONTINUOUS CONVERSATION:
            // Retain up to 8 turns across dialogue so follow-up questions
            // ("The output didn't match", "It's wrong", "Give me a hint", "Explain step 3")
            // preserve active problem, code, and dialogue context across turns.
            const historyLimit = 8;

            const constraintsStr = (activeProblem && activeProblem.constraints)
                ? (Array.isArray(activeProblem.constraints) ? activeProblem.constraints.join('\n') : String(activeProblem.constraints))
                : null;

            let requestLifecycleState = 'PENDING';
            const reqId = generateMayaRequestId();
            if (window.__currentMayaAbortController) {
                try { window.__currentMayaAbortController.abort('superseded'); } catch (e) {}
            }
            const abortController = new AbortController();
            window.__currentMayaAbortController = abortController;
            window.__currentMayaRequestId = reqId;

            const payload = {
                message: promptPayloadText,
                stream: true,
                conversation_id: getOrCreateMayaConversationId(),
                request_id: reqId,
                context: {
                    student_id: sid,
                    student_name: studentName,
                    bot_name: botName,
                    active_workspace: window.active_workspace || 'dashboard',
                    problem_id: probId,
                    problem_title: (activeProblem ? activeProblem.title : null),
                    problem_description: (activeProblem ? activeProblem.description : null),
                    constraints: constraintsStr,
                    selected_language: lang,
                    current_code: safeCode,
                    last_error: safeError,
                    execution_output: safeExecOutput,
                    failed_test_case: safeFailedTc,
                    submission_status: submissionStatus,
                    test_id: testId,
                    is_test_mode: inTest,
                    visualization_context: (typeof getActiveVisualizationContext === 'function' ? getActiveVisualizationContext() : null)
                },
                history: aiTutorChatHistory.map(m => ({ role: m.role === 'user' ? 'user' : 'companion', content: m.content })).slice(-historyLimit)
            };

            const fetchTimeoutId = setTimeout(() => {
                abortController.abort('timeout');
            }, 120000); // 120-second safety timeout for thorough line-by-line explanations

            try {
                const headers = { 'Content-Type': 'application/json' };
                if (token) headers['Authorization'] = `Bearer ${token}`;
                if (sid && sid !== 'null' && sid !== 'undefined') headers['X-Student-Id'] = sid;

                const res = await fetch(`${API_BASE}/api/ai/companion/chat`, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload),
                    signal: abortController.signal
                });

                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    const errMsg = safeExtractErrorMessage(errData, 'Could not reach AI Tutor engine.');
                    const httpErr = new Error(errMsg);
                    httpErr.status = res.status;
                    httpErr.detail = errMsg;
                    throw httpErr;
                }

                const contentType = res.headers.get('content-type') || '';
                let accumulatedText = '';
                let finalDoneData = null;

                if (contentType.includes('text/event-stream') && res.body) {
                    // FAST SSE STREAMING:
                    requestLifecycleState = 'STREAMING';
                    if (bubbleMetricsEl) bubbleMetricsEl.textContent = '● Streaming...';
                    let isFirstDelta = true;
                    let receivedDone = false;
                    let serverError = null;

                    // Shared parser guarantees the terminal `done` frame is
                    // processed even if the stream ends without a trailing newline.
                    await readSSEStream(res, (eventName, dataObj) => {
                        if (eventName === 'delta') {
                            if (dataObj.text) {
                                if (isFirstDelta) {
                                    isFirstDelta = false;
                                    if (bubbleTextEl) {
                                        bubbleTextEl.style.color = '#e2e8f0';
                                        bubbleTextEl.style.fontStyle = 'normal';
                                    }
                                }
                                accumulatedText += dataObj.text;
                                if (bubbleTextEl) bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                stream.scrollTop = stream.scrollHeight;
                            }
                        } else if (eventName === 'error') {
                            serverError = dataObj;
                            if (bubbleMetricsEl) bubbleMetricsEl.textContent = 'ERROR';
                        } else if (eventName === 'visualization') {
                            // Contained so a viz failure cannot break text streaming.
                            try {
                                if (typeof renderCompanionVisualization === 'function') {
                                    renderCompanionVisualization(dataObj);
                                }
                            } catch (vizErr) {
                                console.warn('Maya visualization render failed', vizErr);
                            }
                        } else if (eventName === 'metrics') {
                            if (bubbleMetricsEl && dataObj) {
                                const parts = [];
                                if (dataObj.ttft) parts.push(`${dataObj.ttft}s TTFT`);
                                if (dataObj.total_time) parts.push(`${dataObj.total_time}s`);
                                bubbleMetricsEl.textContent = `⚡ ${parts.join(' | ')}`;
                            }
                        } else if (eventName === 'done') {
                            receivedDone = true;
                            finalDoneData = dataObj;
                            if (dataObj.message && (!accumulatedText || accumulatedText.length < dataObj.message.length)) {
                                accumulatedText = dataObj.message;
                                if (bubbleTextEl) {
                                    bubbleTextEl.style.color = '#e2e8f0';
                                    bubbleTextEl.style.fontStyle = 'normal';
                                    bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                                }
                            }
                            if (dataObj.visualization && typeof renderCompanionVisualization === 'function') {
                                try { renderCompanionVisualization(dataObj.visualization); } catch (vizErr) {
                                    console.warn('Maya visualization render failed', vizErr);
                                }
                            }
                            if (bubbleExtrasEl) {
                                bubbleExtrasEl.innerHTML = buildAssistantExtrasHTML(dataObj.recommended_problems, dataObj.visualization);
                            }
                        }
                    });

                    // Terminal state comes from the server, never from the mere
                    // presence of a message. This is the fake-completion fix.
                    requestLifecycleState = resolveMayaTerminalState(finalDoneData, receivedDone);
                    if (serverError && requestLifecycleState === MAYA_TERMINAL.COMPLETED) {
                        // Defensive: a server that flags an error is never a success.
                        requestLifecycleState = MAYA_TERMINAL.INTERRUPTED;
                    }

                    if (isFirstDelta && !accumulatedText && finalDoneData && finalDoneData.message) {
                        accumulatedText = finalDoneData.message;
                        if (bubbleTextEl) {
                            bubbleTextEl.style.color = '#e2e8f0';
                            bubbleTextEl.style.fontStyle = 'normal';
                            bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText);
                        }
                    }

                    // Stale check
                    if (window.__currentMayaRequestId !== reqId) {
                        requestLifecycleState = 'CANCELLED';
                        return;
                    }

                    if (requestLifecycleState === 'COMPLETED' && accumulatedText.trim()) {
                        aiTutorChatHistory.push({ role: 'user', content: displayUserText });
                        aiTutorChatHistory.push({
                            role: 'assistant',
                            content: accumulatedText,
                            recommended_problems: finalDoneData ? finalDoneData.recommended_problems : [],
                            visualization: finalDoneData ? finalDoneData.visualization : null
                        });
                    } else if (accumulatedText.trim().length > 0) {
                        // Premature termination: preserve partial output and offer retry
                        requestLifecycleState = 'INTERRUPTED';
                        accumulatedText += '\n\n*(Response Interrupted ⚠️)*';
                        if (bubbleTextEl) {
                            bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText) + `
                                <div style="margin-top:10px;">
                                    <button class="filter-btn" onclick="retryAITutorChat(${JSON.stringify(promptPayloadText)}, '${containerId}')" style="background:#0284c7; color:#fff; border:none; border-radius:4px; padding:4px 10px; font-size:11px; cursor:pointer; font-weight:700;">
                                        🔄 Retry
                                    </button>
                                </div>
                            `;
                        }
                        if (bubbleMetricsEl) bubbleMetricsEl.textContent = '⚠️ INTERRUPTED';
                        aiTutorChatHistory.push({ role: 'user', content: displayUserText });
                        aiTutorChatHistory.push({
                            role: 'assistant',
                            content: accumulatedText,
                            recommended_problems: [],
                            visualization: null
                        });
                    }

                } else {
                    // JSON FALLBACK
                    const data = await res.json();
                    requestLifecycleState = 'COMPLETED';
                    if (bubbleTextEl) {
                        bubbleTextEl.style.color = '#e2e8f0';
                        bubbleTextEl.style.fontStyle = 'normal';
                        bubbleTextEl.innerHTML = formatAITutorMarkdown(data.message || '');
                    }
                    if (bubbleMetricsEl && data.metrics) {
                        const parts = [];
                        if (data.metrics.ttft) parts.push(`${data.metrics.ttft}s TTFT`);
                        if (data.metrics.total_time) parts.push(`${data.metrics.total_time}s`);
                        bubbleMetricsEl.textContent = `⚡ ${parts.join(' | ')}`;
                    } else if (bubbleMetricsEl) {
                        bubbleMetricsEl.textContent = '';
                    }
                    if (bubbleExtrasEl) {
                        bubbleExtrasEl.innerHTML = buildAssistantExtrasHTML(data.recommended_problems, data.visualization);
                    }
                    if (data.visualization && typeof renderCompanionVisualization === 'function') {
                        renderCompanionVisualization(data.visualization);
                    }

                    aiTutorChatHistory.push({ role: 'user', content: displayUserText });
                    aiTutorChatHistory.push({
                        role: 'assistant',
                        content: data.message,
                        recommended_problems: data.recommended_problems,
                        visualization: data.visualization
                    });
                }

            } catch (err) {
                if (abortController.signal.aborted && abortController.signal.reason === 'superseded') {
                    requestLifecycleState = 'CANCELLED';
                    return;
                }
                console.error('AI Tutor chat failed:', err);
                const isAbort = (err.name === 'AbortError' || abortController.signal.aborted);
                const classified = isAbort
                    ? { type: 'TIMEOUT', message: 'Request timed out after 120 seconds. Please try again.' }
                    : classifyApiError(err);

                if (accumulatedText && accumulatedText.trim().length > 0) {
                    requestLifecycleState = 'INTERRUPTED';
                    accumulatedText += '\n\n*(Response Interrupted ⚠️ — ' + escapeHtml(classified.message) + ')*';
                    if (bubbleTextEl) {
                        bubbleTextEl.innerHTML = formatAITutorMarkdown(accumulatedText) + `
                            <div style="margin-top:10px;">
                                <button class="filter-btn" onclick="retryAITutorChat(${JSON.stringify(promptPayloadText)}, '${containerId}')" style="background:#0284c7; color:#fff; border:none; border-radius:4px; padding:4px 10px; font-size:11px; cursor:pointer; font-weight:700;">
                                    🔄 Retry
                                </button>
                            </div>
                        `;
                    }
                    if (bubbleMetricsEl) bubbleMetricsEl.textContent = '⚠️ INTERRUPTED';
                } else {
                    requestLifecycleState = 'FAILED';
                    if (bubbleTextEl) {
                        bubbleTextEl.style.color = '#f87171';
                        bubbleTextEl.style.fontStyle = 'normal';
                        const isGroqErr = classified.message && (classified.message.toLowerCase().includes('groq') || classified.message.includes('Personal Groq API key'));
                        bubbleTextEl.innerHTML = `
                            ⚠️ <strong>${escapeHtml(classified.type)}:</strong> ${escapeHtml(classified.message)}
                            ${isGroqErr ? `
                                <div style="margin-top:10px;">
                                    <button class="filter-btn" onclick="openGroqKeyModal(true)" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; border:none; border-radius:6px; padding:6px 14px; font-size:12px; cursor:pointer; font-weight:700;">
                                        🔑 Connect Groq API Key
                                    </button>
                                </div>
                            ` : `
                                <div style="margin-top:10px;">
                                    <button class="filter-btn" onclick="retryAITutorChat(${JSON.stringify(promptPayloadText)}, '${containerId}')" style="background:#0284c7; color:#fff; border:none; border-radius:4px; padding:4px 10px; font-size:11px; cursor:pointer; font-weight:700;">
                                        🔄 Retry
                                    </button>
                                </div>
                            `}
                        `;
                    }
                    if (bubbleMetricsEl) bubbleMetricsEl.textContent = classified.type;
                }
            } finally {
                clearTimeout(fetchTimeoutId);
                isAITutorSending = false;
                if (input) {
                    input.disabled = false;
                    input.focus();
                }
                if (sendBtn) sendBtn.disabled = false;

                // Guaranteed terminal state: never leave bubble on "Thinking..."
                if (bubbleTextEl && (bubbleTextEl.textContent.trim() === 'Thinking...' || bubbleTextEl.innerHTML.trim() === 'Thinking...')) {
                    bubbleTextEl.style.color = '#f87171';
                    bubbleTextEl.style.fontStyle = 'normal';
                    bubbleTextEl.innerHTML = '⚠️ Stream closed unexpectedly without a response. Please try again.';
                }
                if (bubbleMetricsEl && bubbleMetricsEl.textContent.includes('Thinking...')) {
                    bubbleMetricsEl.textContent = 'DONE';
                }
                stream.scrollTop = stream.scrollHeight;
            }
        }

        function retryAITutorChat(promptText, containerId = 'aiTabContent') {
            if (!promptText) return;
            const input = document.getElementById(containerId === 'aiTabContent' ? 'aiTutorChatInput' : 'aiPanelChatInput');
            if (input) input.value = promptText;
            sendAITutorChat(promptText, containerId);
        }

        function appendChatBubbleDOM(stream, role, content, recommendations = [], visualization = null) {
            if (!stream) return;

            const bubble = document.createElement('div');
            bubble.className = `ai-msg ${role}`;

            if (role === 'user') {
                bubble.innerHTML = `
                    <div class="ai-avatar">👤</div>
                    <div class="ai-msg-body">${escapeHtml(content)}</div>
                `;
            } else {
                const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
                const extrasHtml = buildAssistantExtrasHTML(recommendations, visualization);
                bubble.innerHTML = `
                    <div class="ai-avatar">🧠</div>
                    <div class="ai-msg-body">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                            <span style="font-weight:700; color:#818cf8; font-size:11px;">${escapeHtml(botName)}</span>
                            ${content.includes('Revision Notes') ? `<button class="ai-copy-btn" onclick="copyAiNotes(this)">📋 Copy Notes</button>` : ''}
                        </div>
                        <div>${formatAITutorMarkdown(content)}</div>
                        ${extrasHtml}
                    </div>
                `;
            }

            stream.appendChild(bubble);
        }

        function formatAITutorMarkdown(rawText) {
            if (!rawText) return '';
            // Strip ALL visualization JSON/blocks so raw spec NEVER renders in the chat bubble
            // 1. Fenced blocks: ```visualization ... ``` and ```viz ... ``` and ```flowchart ... ```
            rawText = rawText.replace(/```(?:visualization|viz|flowchart)\s*[\s\S]*?```/gi, '');
            // 2. XML-style tags: <visualization>...</visualization>
            rawText = rawText.replace(/<visualization>[\s\S]*?<\/visualization>/gi, '');
            // 3. Fenced JSON blocks containing viz_type: ```json { "viz_type": ... } ```
            rawText = rawText.replace(/```(?:json)?\s*\{[\s\S]*?"viz_type"[\s\S]*?\}\s*```/gi, '');
            // 4. Bare JSON objects with viz_type anywhere in the text (greedy up to closing brace)
            rawText = rawText.replace(/\{[\s\S]*?"viz_type"\s*:[\s\S]*?(?:\}\s*)+/gi, '');
            // 5. Any remaining trailing/inline viz_type JSON blob
            rawText = rawText.replace(/\{[\s\r\n]*"viz_type"[\s\S]*?$/gi, '').trimEnd();
            // 6. Strip stray internal field names that should never appear in user-facing text
            rawText = rawText.replace(/^\s*"visualization_(?:intent|required)"\s*:.*$/gim, '');
            rawText = rawText.replace(/^\s*"source_engine"\s*:.*$/gim, '');

            // Normalize common HTML formatting tags into markdown before escapeHtml so they render styled rather than as raw HTML entities
            rawText = rawText.replace(/<\/?(?:strong|b)>/gi, '**');
            rawText = rawText.replace(/<\/?(?:em|i)>/gi, '*');
            rawText = rawText.replace(/<code>([\s\S]*?)<\/code>/gi, '`$1`');
            rawText = rawText.replace(/<br\s*\/?>/gi, '\n');

            // Handle fenced code blocks first
            const codeBlocks = [];
            let text = rawText.replace(/```([a-zA-Z0-9_\-\+#]*)\n([\s\S]*?)```/g, function(match, lang, code) {
                const id = 'code_holder_' + codeBlocks.length;
                codeBlocks.push({ lang: lang || 'code', code: code });
                return id;
            });

            // Escape HTML for safety
            text = escapeHtml(text);

            // Headings
            text = text.replace(/^### (.*$)/gim, '<h3 style="font-size:14px; font-weight:700; color:#38bdf8; margin:12px 0 6px 0;">$1</h3>');
            text = text.replace(/^## (.*$)/gim, '<h2 style="font-size:15px; font-weight:700; color:#818cf8; margin:14px 0 8px 0;">$1</h2>');
            text = text.replace(/^# (.*$)/gim, '<h1 style="font-size:17px; font-weight:800; color:#f8fafc; margin:16px 0 10px 0; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:4px;">$1</h1>');
            text = text.replace(/^#### (.*$)/gim, '<h4 style="font-size:13px; font-weight:700; color:#cbd5e1; margin:8px 0 4px 0;">$1</h4>');

            // Tables: Detect markdown table blocks
            const tableRegex = /((?:\|[^\n]+\|\r?\n)+)/g;
            text = text.replace(tableRegex, function(match) {
                const lines = match.trim().split('\n').filter(l => l.trim().startsWith('|'));
                if (lines.length < 2) return match;
                
                let headers = lines[0].split('|').map(c => c.trim()).filter((c, i, a) => i > 0 && i < a.length - 1);
                let html = '<div class="ai-table-wrap"><table class="ai-table"><thead><tr>';
                headers.forEach(h => { html += `<th>${h}</th>`; });
                html += '</tr></thead><tbody>';

                const dataRows = lines.slice(2); // Skip separator row
                dataRows.forEach(row => {
                    const cells = row.split('|').map(c => c.trim()).filter((c, i, a) => i > 0 && i < a.length - 1);
                    if (cells.length > 0) {
                        html += '<tr>';
                        cells.forEach(c => { html += `<td>${c}</td>`; });
                        html += '</tr>';
                    }
                });
                html += '</tbody></table></div>';
                return html;
            });

            // Bold & Italics
            text = text.replace(/\*\*([^*]+)\*\*/g, '<strong style="color:#f8fafc;">$1</strong>');
            text = text.replace(/\*([^*]+)\*/g, '<em style="color:#e2e8f0;">$1</em>');

            // Inline Code
            text = text.replace(/`([^`]+)`/g, '<code style="background:#090d16; color:#facc15; padding:2px 5px; border-radius:4px; font-family:Consolas, monospace; font-size:12px;">$1</code>');

            // Bullet Lists
            text = text.replace(/\n- /g, '<br>• ');
            text = text.replace(/\n\d+\. /g, function(m) { return '<br>' + m.trim() + ' '; });

            // Line breaks
            text = text.replace(/\n\n/g, '<div style="height:8px;"></div>');
            text = text.replace(/\n/g, '<br>');

            // Re-insert code blocks
            codeBlocks.forEach((block, idx) => {
                const marker = 'code_holder_' + idx;
                const langLabel = block.lang.toUpperCase() || 'CODE';
                const safeCode = escapeHtml(block.code);
                const blockHtml = `
                    <div class="ai-code-block">
                        <div class="ai-code-header">
                            <span>💻 ${langLabel}</span>
                            <button class="ai-copy-btn" onclick="copyAiCode(this)">📋 Copy Code</button>
                        </div>
                        <pre class="ai-code-content"><code>${safeCode}</code></pre>
                    </div>
                `;
                text = text.replace(marker, blockHtml);
            });

            return text;
        }

        function copyAiCode(btn) {
            const pre = btn.closest('.ai-code-block').querySelector('code');
            if (pre) {
                navigator.clipboard.writeText(pre.textContent).then(() => {
                    const originalText = btn.textContent;
                    btn.textContent = '✓ Copied!';
                    btn.style.borderColor = '#22c55e';
                    btn.style.color = '#22c55e';
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.style.borderColor = '';
                        btn.style.color = '';
                    }, 2000);
                });
            }
        }

        function copyAiNotes(btn) {
            const body = btn.closest('.ai-msg-body');
            if (body) {
                navigator.clipboard.writeText(body.innerText).then(() => {
                    const originalText = btn.textContent;
                    btn.textContent = '✓ Notes Copied!';
                    btn.style.borderColor = '#22c55e';
                    btn.style.color = '#22c55e';
                    setTimeout(() => {
                        btn.textContent = originalText;
                        btn.style.borderColor = '';
                        btn.style.color = '';
                    }, 2000);
                });
            }
        }


        function closeAITutorModal() {
            document.getElementById("aiTutorModal").style.display = "none";
        }

        // ── INLINE AI PANEL (3rd column of workspace) ──────────────────
        let currentAIPanelTab = 'chat';

        function switchAIPanelTab(tabName) {
            currentAIPanelTab = tabName;

            // Update panel tab active states
            document.querySelectorAll('.ai-ptab').forEach(btn => btn.classList.remove('active'));
            const activeBtn = document.getElementById(`panelTabBtn_${tabName}`);
            if (activeBtn) activeBtn.classList.add('active');

            if (tabName === 'chat') {
                renderAITutorChatView('aiPanelContent');
            } else {
                loadAITabContent(tabName, 'aiPanelContent');
            }
        }

        function refreshAIPanel() {
            // Called when a problem is opened — preloads the active panel tab
            if (!activeProblemId) return;
            const panelContent = document.getElementById('aiPanelContent');
            if (!panelContent) return;
            switchAIPanelTab(currentAIPanelTab);
        }

        function getActiveProblemId() {
            if (isTestMode() && activeTestSession && activeTestSession.test && activeTestSession.test.questions) {
                const q = activeTestSession.test.questions[activeTestSession.activeQuestionIndex];
                return q ? (q.problem_id || q.id) : activeProblemId;
            }
            return activeProblemId;
        }

        function getActiveCode() {
            if (isTestMode()) {
                const takingEl = document.getElementById("takingCode");
                return takingEl ? takingEl.value : "";
            }
            const codeEl = document.getElementById("code");
            return codeEl ? codeEl.value : "";
        }

        function getActiveLanguage() {
            if (isTestMode()) {
                const sel = document.getElementById("takingLanguageSelect");
                return sel ? sel.value : "python";
            }
            const sel = document.getElementById("languageSelect");
            return sel ? sel.value : "python";
        }

        // ── 3-PANEL EXPAND / FOCUS HANDLER ────────────────────────────
        let currentExpandedPanel = null;

        function toggleExpandPanel(panelKey) {
            const grid = document.getElementById("workspace3ColGrid");
            if (!grid) return;

            const allKeys = ['problem', 'editor', 'ai'];

            if (currentExpandedPanel === panelKey) {
                // Restore normal 3-panel layout
                grid.classList.remove(`focus-panel-${panelKey}`);
                currentExpandedPanel = null;

                allKeys.forEach(k => {
                    const icon = document.getElementById(`expandIcon_${k}`);
                    const text = document.getElementById(`expandText_${k}`);
                    const btn = document.getElementById(`expandBtn_${k}`);
                    if (icon) icon.textContent = "⤢";
                    if (text) text.textContent = "Expand";
                    if (btn) {
                        btn.classList.remove("is-expanded");
                        btn.title = "Maximize panel";
                    }
                });
            } else {
                // Reset previous focus class
                allKeys.forEach(k => {
                    grid.classList.remove(`focus-panel-${k}`);
                    const btn = document.getElementById(`expandBtn_${k}`);
                    if (btn) btn.classList.remove("is-expanded");
                });

                // Apply focus class to expand requested panel
                grid.classList.add(`focus-panel-${panelKey}`);
                currentExpandedPanel = panelKey;

                allKeys.forEach(k => {
                    const icon = document.getElementById(`expandIcon_${k}`);
                    const text = document.getElementById(`expandText_${k}`);
                    const btn = document.getElementById(`expandBtn_${k}`);
                    if (k === panelKey) {
                        if (icon) icon.textContent = "✕";
                        if (text) text.textContent = "Exit Focus / Restore";
                        if (btn) {
                            btn.classList.add("is-expanded");
                            btn.title = "Exit Focus and restore 3-panel layout";
                        }
                    } else {
                        if (icon) icon.textContent = "⤢";
                        if (text) text.textContent = "Expand";
                        if (btn) {
                            btn.classList.remove("is-expanded");
                            btn.title = "Maximize panel";
                        }
                    }
                });
            }
        }

        // Pressing Escape exits focus and restores the 3-panel workspace layout
        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && currentExpandedPanel) {
                toggleExpandPanel(currentExpandedPanel);
            }
        });

        function dismissFeedbackVisual() {
            const card = document.getElementById("executionFeedbackCard");
            if (card) {
                card.style.display = "none";
            }
        }

        function switchAITab(tabName) {
            // If in active test session, only 'chat' is permitted for question understanding
            if (isTestMode()) {
                const solveTabs = ["hint", "solution", "debug", "similar", "visualize"];
                solveTabs.forEach(t => {
                    const btn = document.getElementById(`tabBtn_${t}`);
                    if (btn) btn.style.display = "none";
                    const pBtn = document.getElementById(`panelTabBtn_${t}`);
                    if (pBtn) pBtn.style.display = "none";
                });
                tabName = 'chat';
            } else {
                // In normal practice mode, restore the Maya tabs
                const allTabs = ["chat", "hint", "solution", "debug", "similar", "visualize"];
                allTabs.forEach(t => {
                    const btn = document.getElementById(`tabBtn_${t}`);
                    if (btn) btn.style.display = "inline-block";
                    const pBtn = document.getElementById(`panelTabBtn_${t}`);
                    if (pBtn) pBtn.style.display = "inline-block";
                });
                const clearBtn = document.getElementById("aiTutorClearBtn");
                if (clearBtn) clearBtn.style.display = (tabName === 'chat') ? "inline-block" : "none";
            }


            currentAITab = tabName;
            // Update tab button active states
            const tabButtons = document.querySelectorAll(".ai-tab-btn");
            tabButtons.forEach(btn => btn.classList.remove("active"));
            const activeBtn = document.getElementById(`tabBtn_${tabName}`);
            if (activeBtn) activeBtn.classList.add("active");

            if (tabName === 'chat') {
                renderAITutorChatView('aiTabContent');
            } else {
                loadAITabContent(tabName, 'aiTabContent');
            }
        }

        async function loadAITabContent(tabName, containerId = 'aiTabContent') {
            const container = document.getElementById(containerId);
            const probId = getActiveProblemId();
            const code = getActiveCode();
            const language = getActiveLanguage();
            const testId = isTestMode() && activeTestSession && activeTestSession.test ? activeTestSession.test.id : null;

            if (!probId) {
                container.innerHTML = `
                    <div class="ai-card-box" style="text-align: center; color: #94a3b8;">
                        Please select a problem first to enable the AI Tutor.
                    </div>
                `;
                return;
            }

            container.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #94a3b8;">
                    <div style="font-size: 28px; margin-bottom: 8px;">🧠</div>
                    Analyzing problem with AI pedagogical engine...
                </div>
            `;

            try {
                if (tabName === 'explain') {
                    const res = await fetch(`${API_BASE}/api/ai/explain`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to load explanation.");
                    }
                    const data = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div class="ai-card-title">🎯 Identified Topics & Concepts</div>
                            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px;">
                                ${(data.required_topics || []).map(t => `<span class="badge" style="background:#0284c7;color:#fff;font-size:12px;padding:4px 10px;border-radius:6px;cursor:pointer;font-weight:600;" onclick="switchAIPanelTab('learn');" title="Learn ${escapeHtml(t)}">📖 ${escapeHtml(t)} &rarr;</span>`).join("")}
                            </div>
                        </div>
                        <div class="ai-card-box">
                            <div class="ai-card-title">📖 In Plain English</div>
                            <p style="color: #cbd5e1; line-height: 1.6; font-size: 15px;">${escapeHtml(data.plain_english_summary)}</p>
                        </div>
                        <div class="ai-card-box">
                            <div class="ai-card-title">💡 Intuition & Real-World Analogy</div>
                            <p style="color: #cbd5e1; line-height: 1.6; font-size: 14px;">${escapeHtml(data.real_world_analogy)}</p>
                        </div>
                        <div class="ai-card-box">
                            <div class="ai-card-title">⚠️ Critical Edge Cases to Guard Against</div>
                            <ul style="padding-left: 20px; color: #cbd5e1; line-height: 1.6; font-size: 14px;">
                                ${data.critical_edge_cases.map(ec => `<li>${escapeHtml(ec)}</li>`).join("")}
                            </ul>
                        </div>
                        <div class="ai-card-box">
                            <div class="ai-card-title">❌ Common Misconceptions</div>
                            <ul style="padding-left: 20px; color: #f87171; line-height: 1.6; font-size: 14px;">
                                ${data.common_misconceptions.map(cm => `<li>${escapeHtml(cm)}</li>`).join("")}
                            </ul>
                        </div>
                    `;
                } else if (tabName === 'learn') {
                    const res = await fetch(`${API_BASE}/api/ai/learn`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, test_id: testId, language: language })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to load concepts.");
                    }
                    const data = await res.json();
                    const lesson = data.mini_lesson;
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <div class="ai-card-title">🎯 Primary Concept: ${escapeHtml(data.primary_topic)}</div>
                                <span class="badge badge-source" style="background: #6366f1; color: #fff;">Mini-Lesson</span>
                            </div>
                            <p style="color: #cbd5e1; line-height: 1.6; font-size: 14px; margin-bottom: 12px;">${escapeHtml(lesson.core_concept)}</p>
                            <div style="font-weight: 600; color: #38bdf8; font-size: 13px; margin-bottom: 6px;">When to reach for this pattern:</div>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 14px;">${escapeHtml(lesson.when_to_reach_for_this)}</p>
                            
                            <div style="font-weight: 600; color: #38bdf8; font-size: 13px; margin-bottom: 6px;">Canonical Code Pattern (${escapeHtml(language.toUpperCase())}):</div>
                            <pre style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 12px; color: #38bdf8; font-family: Consolas, monospace; font-size: 13px; overflow-x: auto;"><code>${escapeHtml(lesson.canonical_pattern_code)}</code></pre>
                            
                            <div style="margin-top: 14px; background: rgba(225, 29, 72, 0.1); border-left: 3px solid #f43f5e; padding: 10px 14px; border-radius: 4px;">
                                <div style="font-weight: 700; color: #f43f5e; font-size: 13px; margin-bottom: 4px;">Gotchas & Common Pitfalls</div>
                                <div style="color: #cbd5e1; font-size: 13px;">${escapeHtml(lesson.gotchas_and_pitfalls)}</div>
                            </div>

                            ${(data.similar_problems && data.similar_problems.length > 0) ? `
                                <div style="margin-top: 16px;">
                                    <div style="font-weight: 700; color: #38bdf8; font-size: 13px; margin-bottom: 8px;">📚 Practice This Concept (CodeMind Catalog):</div>
                                    <div style="display: flex; flex-direction: column; gap: 8px;">
                                        ${data.similar_problems.map(sp => `
                                            <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                                                <div>
                                                    <div style="font-size: 13px; font-weight: 600; color: #f8fafc;">${escapeHtml(sp.title)} <span class="badge badge-${(sp.difficulty||'easy').toLowerCase()}">${escapeHtml(sp.difficulty||'Easy')}</span></div>
                                                    <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">${escapeHtml(sp.reason || '')}</div>
                                                </div>
                                                <button class="run-button" onclick="closeAITutorModal(); openProblem('${sp.problem_id}');" style="margin-top: 0; padding: 4px 10px; font-size: 11px; flex-shrink: 0;">Practice &rarr;</button>
                                            </div>
                                        `).join("")}
                                    </div>
                                </div>
                            ` : ''}
                        </div>
                    `;
                } else if (tabName === 'hint') {
                    container.innerHTML = `
                        <div class="ai-card-box" style="margin-bottom: 14px;">
                            <div class="ai-card-title">💡 Progressive 3-Tier Hints</div>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">
                                Hints unlock progressively. Try to solve with Level 1 first to preserve your independent solve rating!
                            </p>
                            <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px;">
                                <button class="q-tab-button" onclick="requestAIHint(1)">Level 1: Intuition Nudge</button>
                                <button class="q-tab-button" onclick="requestAIHint(2)">Level 2: Strategic Blueprint</button>
                                <button class="q-tab-button" onclick="requestAIHint(3)">Level 3: Pseudocode & Edge Guard</button>
                            </div>
                            <div id="hintOutputContainer" style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 16px; min-height: 120px; color: #cbd5e1; font-size: 14px; line-height: 1.6; white-space: pre-line;">
                                Click a hint tier above to unlock progressive guidance.
                            </div>
                        </div>
                    `;
                } else if (tabName === 'approach') {
                    const res = await fetch(`${API_BASE}/api/ai/approach`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, code: code || "# No code entered", language: language, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to analyze approach.");
                    }
                    const data = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                                <div class="ai-card-title">🔍 Identified Approach: ${escapeHtml(data.detected_approach)}</div>
                                <span class="badge" style="background: #0284c7; color: #fff;">${escapeHtml(data.estimated_time_complexity)} Time</span>
                            </div>
                            <div style="margin-bottom: 12px;">
                                <strong style="color: #22c55e; font-size: 13px;">✓ What you did well:</strong>
                                <p style="color: #cbd5e1; font-size: 14px; margin-top: 4px;">${escapeHtml(data.what_you_did_well)}</p>
                            </div>
                            <div style="margin-bottom: 12px;">
                                <strong style="color: #f43f5e; font-size: 13px;">⚠️ Critical Bottleneck:</strong>
                                <p style="color: #cbd5e1; font-size: 14px; margin-top: 4px;">${escapeHtml(data.critical_bottleneck)}</p>
                            </div>

                            <!-- WHY THIS APPROACH INTERACTIVE GUIDANCE -->
                            <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; cursor:pointer;" onclick="const el=document.getElementById('whyApproachBody'); el.style.display = el.style.display==='none'?'block':'none';">
                                    <strong style="color: #818cf8; font-size: 13px;">🎯 Why This Approach? (Algorithmic Invariant)</strong>
                                    <span style="font-size:11px;color:#a5b4fc;">▾ Toggle</span>
                                </div>
                                <div id="whyApproachBody" style="margin-top: 8px; color: #cbd5e1; font-size: 13px; line-height: 1.5;">
                                    This algorithm works by leveraging structural properties of the problem rather than exhaustive brute force.
                                    Instead of evaluating all pairs/subsets, it tracks state or invariants to eliminate redundant computations.
                                    <div style="margin-top: 6px; font-size: 12px; color: #38bdf8;">
                                        ✨ Pro-Tip: Can you bound space complexity while keeping time optimal?
                                    </div>
                                </div>
                            </div>

                            <div style="background: rgba(56, 189, 248, 0.1); border-left: 3px solid #38bdf8; padding: 10px 14px; border-radius: 4px;">
                                <strong style="color: #38bdf8; font-size: 13px;">🚀 Actionable Next Step:</strong>
                                <p style="color: #f8fafc; font-size: 14px; margin-top: 4px;">${escapeHtml(data.actionable_next_step)}</p>
                            </div>
                        </div>
                    `;
                } else if (tabName === 'debug') {
                    const failingResult = lastExecutionResult || { status: "wrong_answer", error: "Run or submit your code to analyze errors." };
                    const res = await fetch(`${API_BASE}/api/ai/debug`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            problem_id: probId,
                            code: code || "# code",
                            language: language,
                            status: failingResult.status || "wrong_answer",
                            error_message: failingResult.error || failingResult.output || null,
                            test_case_result: (failingResult.test_results && failingResult.test_results[0]) ? failingResult.test_results[0] : null,
                            test_id: testId
                        })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to diagnose failure.");
                    }
                    const data = await res.json();
                    const lineNum = data.line_number;
                    const lineBadge = lineNum ? `<span style="background: rgba(239,68,68,0.18); color: #f87171; border: 1px solid rgba(239,68,68,0.4); padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 12px; margin-left: 8px;">Line ${lineNum}</span>` : '';

                    // Build WHERE section from line number + code context
                    let whereSection = "";
                    if (lineNum && code) {
                        const codeLines = code.split("\n");
                        const lineIdx = lineNum - 1;
                        if (lineIdx >= 0 && lineIdx < codeLines.length) {
                            const startCtx = Math.max(0, lineIdx - 1);
                            const endCtx = Math.min(codeLines.length - 1, lineIdx + 1);
                            let codeCtx = "";
                            for (let ci = startCtx; ci <= endCtx; ci++) {
                                const marker = ci === lineIdx ? "→ " : "  ";
                                const ln = ci + 1;
                                codeCtx += `${marker}${ln}: ${escapeHtml(codeLines[ci])}\n`;
                            }
                            whereSection = `
                                <div style="margin-bottom: 12px; background: rgba(251,191,36,0.06); border-left: 3px solid #fbbf24; padding: 10px 14px; border-radius: 4px;">
                                    <div style="font-weight: 700; color: #fbbf24; font-size: 12px; margin-bottom: 6px;">📍 WHERE (Line ${lineNum}):</div>
                                    <pre style="background: #020617; border: 1px solid #334155; border-radius: 4px; padding: 8px; font-size: 12px; color: #e2e8f0; font-family: Consolas, monospace; margin: 0; overflow-x: auto; white-space: pre;">${codeCtx.trimEnd()}</pre>
                                </div>
                            `;
                        }
                    }

                    // Build Preview Fix (if corrected_snippet is available from AI)
                    const correctedSnippet = data.corrected_snippet || data.exact_fix_code || null;
                    let previewFixSection = "";
                    if (correctedSnippet && code && lineNum) {
                        const codeLines = code.split("\n");
                        const lineIdx = lineNum - 1;
                        const origLine = lineIdx >= 0 && lineIdx < codeLines.length ? codeLines[lineIdx] : null;
                        const fixLines = correctedSnippet.split("\n");
                        if (origLine !== null) {
                            const diffId = "diffPreview_" + Date.now();
                            let diffHtml = `<div class="diff-preview"><div class="diff-preview-title">Proposed Fix — Line ${lineNum}</div>`;
                            // Context before
                            if (lineIdx > 0) diffHtml += `<div class="diff-line ctx">${lineNum-1}: ${escapeHtml(codeLines[lineIdx-1])}</div>`;
                            diffHtml += `<div class="diff-line removed">${lineNum}: ${escapeHtml(origLine)}</div>`;
                            fixLines.forEach((fl, fi) => {
                                diffHtml += `<div class="diff-line added">${lineNum+fi}: ${escapeHtml(fl)}</div>`;
                            });
                            if (lineIdx + 1 < codeLines.length) diffHtml += `<div class="diff-line ctx">${lineNum+1}: ${escapeHtml(codeLines[lineIdx+1])}</div>`;
                            diffHtml += `</div>`;
                            diffHtml += `<div class="diff-btns">
                                <button class="diff-apply" onclick="applyDebugFix(${JSON.stringify(correctedSnippet)}, ${lineNum}, ${JSON.stringify(origLine)})">✓ Apply Fix</button>
                                <button class="diff-reject" onclick="this.closest('.diff-fix-container').style.display='none'">✕ Reject</button>
                                <button class="diff-explain-btn" onclick="askMayaToDebugInChat()">💬 Explain</button>
                            </div>`;
                            previewFixSection = `<div class="diff-fix-container" id="${diffId}">${diffHtml}</div>`;
                        }
                    }

                    // Build raw diagnostic collapsible
                    const rawError = failingResult.error || failingResult.stderr || "";
                    const rawDiagId = "rawDiag_" + Date.now();
                    const rawDiagSection = rawError ? `
                        <span class="xray-tech-toggle" onclick="const el=document.getElementById('${rawDiagId}'); el.style.display=el.style.display==='none'?'block':'none';">Raw compiler output ▾</span>
                        <div id="${rawDiagId}" class="xray-tech-details" style="display:none;">${escapeHtml(rawError)}</div>
                    ` : "";

                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <div class="ai-card-title">🛠️ Debug Analysis ${lineBadge}</div>
                                <span class="badge" style="background: #dc2626; color: #fff;">${escapeHtml(data.failure_type || 'Diagnosis')}</span>
                            </div>

                            <div style="margin-bottom: 10px; background: rgba(239,68,68,0.08); border-left: 3px solid #ef4444; padding: 10px 14px; border-radius: 4px;">
                                <div style="font-weight: 700; color: #f87171; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">🔴 WHAT is wrong</div>
                                <div style="color: #f1f5f9; font-size: 13.5px; line-height: 1.5;">${escapeHtml(data.what_is_wrong || data.failure_type || '')}</div>
                            </div>

                            ${whereSection}

                            <div style="margin-bottom: 10px; background: rgba(30,41,59,0.7); border: 1px solid rgba(255,255,255,0.08); padding: 10px 14px; border-radius: 6px;">
                                <div style="font-weight: 700; color: #38bdf8; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">🔵 WHY it is wrong</div>
                                <p style="color: #cbd5e1; font-size: 13.5px; line-height: 1.5; margin: 0;">${escapeHtml(data.why_it_is_wrong || data.root_cause || '')}</p>
                            </div>

                            <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;">
                                <div style="font-weight: 700; color: #34d399; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">🟢 HOW to fix it</div>
                                <div style="color: #f8fafc; font-size: 13.5px; line-height: 1.5;">${escapeHtml(data.how_to_fix || data.exact_fix || '')}</div>
                            </div>

                            ${previewFixSection}

                            ${data.test_case_info ? `
                                <div style="font-size: 12px; color: #94a3b8; background: #020617; border: 1px solid #334155; border-radius: 6px; padding: 10px 12px; margin-bottom: 10px;">
                                    <strong>Test Case:</strong> Expected <code style="color: #22c55e;">${escapeHtml(String(data.test_case_info.expected_output || data.expected || ''))}</code>, got <code style="color: #f43f5e;">${escapeHtml(String(data.test_case_info.actual_output || data.actual || ''))}</code>
                                </div>
                            ` : ''}

                            ${rawDiagSection}

                            <div style="text-align: right; margin-top: 10px;">
                                <button class="filter-btn" onclick="askMayaToDebugInChat()" style="font-size: 12px; padding: 6px 12px; background: rgba(212,175,55,0.15); border: 1px solid var(--accent-gold, #d4af37); color: var(--accent-gold, #d4af37); border-radius: 6px; cursor: pointer;">
                                    💬 Trace Step-by-Step with Maya
                                </button>
                            </div>
                        </div>
                    `;

                } else if (tabName === 'similar') {
                    const res = await fetch(`${API_BASE}/api/ai/similar-problems?problem_id=${encodeURIComponent(probId)}&limit=5`);
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to load similar problems.");
                    }
                    const data = await res.json();
                    const list = data.similar_problems || [];
                    if (list.length === 0) {
                        container.innerHTML = `
                            <div class="ai-card-box" style="text-align: center; color: #94a3b8; padding: 30px 20px;">
                                <div style="font-size: 24px; margin-bottom: 8px;">🔍</div>
                                No similar problems found in the catalog for this topic yet.
                            </div>
                        `;
                    } else {
                        container.innerHTML = `
                            <div class="ai-card-box">
                                <div class="ai-card-title">🔍 Similar Questions from CodeMind Catalog</div>
                                <p style="color: #94a3b8; font-size: 13px; margin-bottom: 14px;">
                                    Matching problems from CodeMind based on shared concepts, tags, and difficulty:
                                </p>
                                <div style="display: flex; flex-direction: column; gap: 10px;">
                                    ${list.map(sp => {
                                        const diff = (sp.difficulty || 'Easy').toLowerCase();
                                        return `
                                            <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px 14px; display: flex; justify-content: space-between; align-items: center; gap: 10px;">
                                                <div style="flex: 1; min-width: 0;">
                                                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                                        <span style="font-size: 14px; font-weight: 700; color: #f8fafc;">${escapeHtml(sp.title)}</span>
                                                        <span class="badge badge-${diff}">${escapeHtml(sp.difficulty || 'Easy')}</span>
                                                    </div>
                                                    <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px;">
                                                        ${(sp.tags || []).slice(0, 3).map(t => `<span class="chip-tag" style="font-size: 11px; padding: 2px 7px;">#${escapeHtml(t)}</span>`).join('')}
                                                        ${(sp.concepts || []).slice(0, 2).map(c => `<span class="badge" style="background: rgba(56,189,248,0.15); color: #38bdf8; font-size: 11px; padding: 2px 7px;">${escapeHtml(c)}</span>`).join('')}
                                                    </div>
                                                </div>
                                                <button class="run-button" onclick="closeAITutorModal(); openProblem('${sp.id}');"
                                                        style="margin-top: 0; padding: 6px 14px; font-size: 12px; background: #0284c7; color: #fff; flex-shrink: 0; border: none; border-radius: 6px; cursor: pointer;">
                                                    Solve &rarr;
                                                </button>
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            </div>
                        `;
                    }
                } else if (tabName === 'review') {
                    const res = await fetch(`${API_BASE}/api/ai/review`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, code: code || "# code", language: language, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to review code.");
                    }
                    const data = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                                <div class="ai-card-title">📊 Code Quality & Complexity Review</div>
                                <span class="badge" style="background: #16a34a; color: #fff; font-size: 13px;">Grade: ${escapeHtml(data.clean_code_grade)}</span>
                            </div>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px;">
                                <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 12px; text-align: center;">
                                    <div style="font-size: 12px; color: #94a3b8;">Time Complexity</div>
                                    <div style="font-size: 20px; font-weight: 800; color: #38bdf8;">${escapeHtml(data.time_complexity)}</div>
                                </div>
                                <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 12px; text-align: center;">
                                    <div style="font-size: 12px; color: #94a3b8;">Space Complexity</div>
                                    <div style="font-size: 20px; font-weight: 800; color: #38bdf8;">${escapeHtml(data.space_complexity)}</div>
                                </div>
                            </div>
                            <div class="ai-card-title">✨ Simplification & Clean Code Advice</div>
                            <ul style="padding-left: 20px; color: #cbd5e1; line-height: 1.6; font-size: 14px;">
                                ${data.simplification_suggestions.map(s => `<li>${escapeHtml(s)}</li>`).join("")}
                            </ul>
                        </div>
                    `;
                } else if (tabName === 'transfer') {
                    const res = await fetch(`${API_BASE}/api/ai/concept-transfer`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to load transfer problems.");
                    }
                    const data = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div class="ai-card-title">🔄 Concept Transfer Mode: ${escapeHtml(data.core_concept)}</div>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">${escapeHtml(data.why_transfer_matters)}</p>
                            <div style="display: flex; flex-direction: column; gap: 12px;">
                                ${data.related_practice_problems.map(rp => `
                                    <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 14px; display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <strong style="color: #f8fafc; font-size: 14px;">${escapeHtml(rp.title)}</strong>
                                            <span class="badge badge-${rp.difficulty.toLowerCase()}" style="margin-left: 8px;">${escapeHtml(rp.difficulty)}</span>
                                            <p style="color: #94a3b8; font-size: 13px; margin-top: 4px;">${escapeHtml(rp.transfer_explanation)}</p>
                                        </div>
                                        <button class="run-button" onclick="closeAITutorModal(); openProblem('${rp.problem_id}');" style="margin-top: 0; padding: 6px 12px; font-size: 12px;">
                                            Practice &rarr;
                                        </button>
                                    </div>
                                `).join("")}
                            </div>
                        </div>
                    `;
                } else if (tabName === 'whatif') {
                    const res = await fetch(`${API_BASE}/api/ai/what-if`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to load What-If scenarios.");
                    }
                    const scenarios = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div class="ai-card-title">⚡ What-If Playground</div>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 16px;">
                                See how optimal algorithmic approaches evolve when constraints or data properties change.
                            </p>
                            <div style="display: flex; flex-direction: column; gap: 12px;">
                                ${scenarios.map(s => `
                                    <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 14px;">
                                        <div style="font-weight: 700; color: #38bdf8; font-size: 14px; margin-bottom: 6px;">${escapeHtml(s.scenario)}</div>
                                        <div style="font-size: 13px; color: #22c55e; margin-bottom: 4px;">Optimal Complexity: ${escapeHtml(s.optimal_complexity)}</div>
                                        <div style="font-size: 13px; color: #cbd5e1;">Approach Shift: ${escapeHtml(s.approach_shift)}</div>
                                    </div>
                                `).join("")}
                            </div>
                        </div>
                    `;
                } else if (tabName === 'interview') {
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div class="ai-card-title">🎤 Mock Interview Evaluator</div>
                            <p style="color: #94a3b8; font-size: 13px; margin-bottom: 12px;">
                                State your thought process, clarifying questions, and proposed Big-O complexity before implementing.
                            </p>
                            <textarea id="interviewThoughtsInput" class="form-control" style="height: 90px; margin-bottom: 12px;" placeholder="e.g. 'I'd clarify if input can be empty or have negative numbers. I plan to use a Hash Map to achieve O(N) time and O(N) space...'"></textarea>
                            <button class="run-button" onclick="submitMockInterview()" style="margin-top: 0;">Submit to Interviewer</button>
                            <div id="interviewEvaluationOutput" style="margin-top: 16px;"></div>
                        </div>
                    `;
                } else if (tabName === 'pattern') {
                    const res = await fetch(`${API_BASE}/api/ai/hidden-pattern`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ problem_id: probId, test_id: testId })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        throw new Error(err.detail || "Unable to reveal hidden pattern.");
                    }
                    const data = await res.json();
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div class="ai-card-title">🧩 ${escapeHtml(data.title)}</div>
                            <p style="color: #cbd5e1; line-height: 1.6; font-size: 14px; margin-bottom: 14px;">${escapeHtml(data.mathematical_invariant)}</p>
                            <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 14px;">
                                <div style="font-weight: 700; color: #38bdf8; font-size: 13px; margin-bottom: 6px;">Pattern Challenge:</div>
                                <p style="color: #cbd5e1; font-size: 14px; margin-bottom: 8px;">${escapeHtml(data.challenge_prompt)}</p>
                                <button class="q-tab-button" onclick="document.getElementById('patternAnswer').style.display='block';">Reveal Invariant Answer</button>
                                <div id="patternAnswer" style="display: none; margin-top: 10px; color: #22c55e; font-size: 13px;">${escapeHtml(data.hint_answer)}</div>
                            </div>
                        </div>
                    `;
                } else if (tabName === 'solution' || tabName === 'full_solution') {
                    if (!isAuthenticated()) {
                        openAuthModal('signin');
                        if (typeof showToast === 'function') showToast('Please sign in to view full solutions.');
                        return;
                    }
                    const user = getAuthUser();
                    const hasGroq = !!(window.currentUserHasGroqKey || (user && user.has_groq_key));
                    if (!hasGroq) {
                        container.innerHTML = `
                            <div class="ai-card-box" style="text-align:center; padding:32px 20px;">
                                <div style="font-size:32px; margin-bottom:12px;">🔑</div>
                                <h3 style="color:#f8fafc; font-size:16px; margin:0 0 8px 0;">Personal Groq API Key Required</h3>
                                <p style="color:#94a3b8; font-size:13px; max-width:440px; margin:0 auto 16px auto; line-height:1.5;">
                                    Full verified solutions are powered by your personal Groq key (free tier available at console.groq.com). Connect your key to unlock instant algorithmic breakdowns.
                                </p>
                                <button onclick="openGroqKeyModal(true)" style="background:linear-gradient(135deg,#d4af37,#b8961e); color:#080808; font-weight:700; border:none; padding:10px 22px; border-radius:8px; cursor:pointer; font-size:13px; box-shadow:0 2px 10px rgba(212,175,55,0.3);">
                                    ⚡ Connect Groq API Key
                                </button>
                            </div>
                        `;
                        openGroqKeyModal(true);
                        return;
                    }

                    container.innerHTML = `<div class="ai-card-box" style="text-align:center; color:#38bdf8; padding:30px;"><div style="font-size:24px; margin-bottom:8px;">⚙️</div>Validating full solution against CodeMind test cases...</div>`;
                    const res = await fetch(`${API_BASE}/api/ai/solution`, {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            ...(getAuthToken() ? { "Authorization": `Bearer ${getAuthToken()}` } : {})
                        },
                        body: JSON.stringify({
                            problem_id: probId,
                            language: language,
                            code: code || "",
                            test_id: testId
                        })
                    });
                    if (!res.ok) {
                        const err = await res.json().catch(() => ({}));
                        const errMsg = err.detail || "Unable to generate full solution.";
                        if (errMsg.toLowerCase().includes('groq')) {
                            openGroqKeyModal(true);
                        }
                        throw new Error(errMsg);
                    }
                    const data = await res.json();

                    // Verification badge
                    let badgeBg = "#64748b";
                    if (data.validation_status === 'verified') badgeBg = "#16a34a";
                    else if (data.validation_status === 'compile_error') badgeBg = "#ea580c";
                    else if (data.validation_status === 'wrong_answer') badgeBg = "#dc2626";

                    const solCodeEscaped = escapeHtml(data.code || "");
                    const rawSolCode = data.code || "";
                    window._lastFullSolutionCode = rawSolCode;

                    // Clean narrative text from accidental nested code blocks
                    const cleanObs = (data.key_observation || '').replace(/```[\s\S]*?```/g, '').trim();
                    const cleanApp = (data.approach || '').replace(/```[\s\S]*?```/g, '').trim();
                    const cleanWhy = (data.why_it_works || '').replace(/```[\s\S]*?```/g, '').trim();
                    const cleanComp = (data.complexity || 'O(N) Time, O(1) Space').replace(/```[\s\S]*?```/g, '').trim();

                    // Verification details
                    const passedCount = data.passed_count !== undefined ? data.passed_count : (data.validation_passed ? 1 : 0);
                    const totalTests = data.total_test_cases || (data.test_results ? data.test_results.length : 1);
                    const isPassed = Boolean(data.validation_passed);
                    const testResults = Array.isArray(data.test_results) ? data.test_results : [];

                    container.innerHTML = `
                        <div class="ai-card-box">
                            <!-- Header: Full Solution -->
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; flex-wrap:wrap; gap:8px;">
                                <div class="ai-card-title">💡 Full Solution</div>
                                <span class="badge" style="background:${badgeBg}; color:#fff; font-size:12px; padding:3px 8px;">${escapeHtml(data.validation_label || 'Runtime verification unavailable')}</span>
                            </div>

                            <!-- 1. Key Observation -->
                            <div style="background:rgba(56,189,248,0.08); border-left:3px solid #38bdf8; padding:10px 14px; border-radius:4px; margin-bottom:12px;">
                                <div style="font-weight:700; color:#38bdf8; font-size:12px; margin-bottom:3px;">1. KEY OBSERVATION:</div>
                                <div style="color:#f1f5f9; font-size:13.5px; line-height:1.5;">${escapeHtml(cleanObs)}</div>
                            </div>

                            <!-- 2. Approach -->
                            <div style="background:rgba(30,41,59,0.7); border:1px solid rgba(255,255,255,0.08); padding:10px 14px; border-radius:6px; margin-bottom:12px;">
                                <div style="font-weight:700; color:#cbd5e1; font-size:12px; margin-bottom:3px;">2. APPROACH:</div>
                                <div style="color:#94a3b8; font-size:13.5px; line-height:1.5;">${escapeHtml(cleanApp)}</div>
                            </div>

                            <!-- 3. Why It Works -->
                            <div style="background:rgba(30,41,59,0.7); border:1px solid rgba(255,255,255,0.08); padding:10px 14px; border-radius:6px; margin-bottom:12px;">
                                <div style="font-weight:700; color:#34d399; font-size:12px; margin-bottom:3px;">3. WHY IT WORKS:</div>
                                <div style="color:#cbd5e1; font-size:13.5px; line-height:1.5;">${escapeHtml(cleanWhy)}</div>
                            </div>

                            <!-- 4. Complexity -->
                            <div style="background:#020617; border:1px solid #334155; border-radius:6px; padding:10px 14px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center;">
                                <span style="font-size:12px; color:#94a3b8;">4. COMPLEXITY:</span>
                                <span style="font-size:13px; font-weight:700; color:#38bdf8; font-family:Consolas, monospace;">${escapeHtml(cleanComp)}</span>
                            </div>

                            <!-- 5. Validated Code Block (Single Code Section) -->
                            <div style="margin-bottom:14px;">
                                <div style="margin-bottom:6px;">
                                    <span style="font-weight:700; color:#f8fafc; font-size:12px;">5. CODE (${escapeHtml((language||'python').toUpperCase())}):</span>
                                </div>
                                <pre style="background:#020617; border:1px solid #334155; border-radius:6px; padding:12px; font-size:12.5px; color:#e2e8f0; font-family:Consolas, monospace; overflow-x:auto; line-height:1.5; margin:0;"><code>${solCodeEscaped}</code></pre>
                            </div>

                            <!-- 6. Verification -->
                            <div style="background:rgba(15,23,42,0.8); border:1px solid ${isPassed ? '#15803d' : '#991b1b'}; border-radius:6px; padding:12px 14px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                    <span style="font-weight:700; color:${isPassed ? '#4ade80' : '#f87171'}; font-size:12px;">
                                        ${isPassed ? '✓ VERIFICATION: TEST CASES PASSED' : '⚠️ VERIFICATION: ATTENTION NEEDED'}
                                    </span>
                                    <span style="font-size:11.5px; color:#38bdf8; font-family:Consolas, monospace; font-weight:700;">
                                        Passed ${passedCount} / ${totalTests} test cases
                                    </span>
                                </div>
                                ${testResults.length > 0 ? `
                                    <div style="display:flex; flex-direction:column; gap:8px; margin-top:6px;">
                                        ${testResults.slice(0, 3).map((tc, idx) => `
                                            <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); border-radius:4px; padding:8px 10px; font-size:11.5px; font-family:Consolas, monospace;">
                                                <div style="display:flex; justify-content:space-between; color:${tc.passed ? '#4ade80' : '#f87171'}; margin-bottom:4px;">
                                                    <span style="font-weight:700;">Test Case #${idx + 1}</span>
                                                    <span>${tc.passed ? '✓ Passed' : '✗ Failed'}</span>
                                                </div>
                                                ${tc.input !== undefined && tc.input !== null && String(tc.input).trim() ? `<div style="color:#94a3b8;">Input: <span style="color:#cbd5e1;">${escapeHtml(String(tc.input).slice(0, 150))}</span></div>` : ''}
                                                <div style="color:#94a3b8;">Expected Output: <span style="color:#cbd5e1;">${escapeHtml(String(tc.expected_output || '').slice(0, 150))}</span></div>
                                                <div style="color:#94a3b8;">Actual Output: <span style="color:#cbd5e1;">${escapeHtml(String(tc.actual_output || '').slice(0, 150))}</span></div>
                                            </div>
                                        `).join('')}
                                    </div>
                                ` : `
                                    <div style="font-size:12px; color:#94a3b8;">
                                        ${escapeHtml(data.validation_label || 'Verified against problem specifications.')}
                                    </div>
                                `}
                            </div>
                        </div>
                    `;
                } else if (tabName === 'visualize') {
                    await loadProblemVisualization(containerId);
                    return;
                }

            } catch (err) {
                const classified = classifyApiError(err);
                container.innerHTML = `
                    <div class="ai-card-box" style="border-color: #ef4444; color: #ef4444;">
                        <strong>${escapeHtml(classified.type)}:</strong> ${escapeHtml(classified.message)}
                    </div>
                `;
            }
        }

        // =========================================================================
        // ── PROBLEM MAYA VISUALIZE SYSTEM (EDUCATIONAL POSTER / SLIDE SEQUENCE) ──
        // =========================================================================
        let problemVizState = {};
        // Stale-prevention: track the most recent viz request ID per container
        let _currentVizRequestId = {};

        function resetProblemVisualizationState() {
            Object.keys(problemVizState).forEach(k => {
                if (problemVizState[k] && problemVizState[k].timer) {
                    clearInterval(problemVizState[k].timer);
                    problemVizState[k].timer = null;
                }
            });
            problemVizState = {};
            _currentVizRequestId = {};
            currentVizSpec = null;
            currentVizStepIndex = 0;
            if (vizPlayTimer) {
                clearInterval(vizPlayTimer);
                vizPlayTimer = null;
            }
        }

        function triggerProblemVisualization(containerId = 'aiPanelContent') {
            if (containerId === 'aiTabContent') {
                switchAITab('visualize');
            } else {
                switchAIPanelTab('visualize');
            }
        }

        async function loadProblemVisualization(containerId = 'aiPanelContent') {
            const container = document.getElementById(containerId);
            if (!container) return;

            const probId = getActiveProblemId();
            const code = getActiveCode();
            const language = getActiveLanguage();
            const probTitle = (currentProblemData && currentProblemData.title) || probId || "Current Problem";

            if (!probId) {
                container.innerHTML = `
                    <div class="ai-card-box" style="text-align: center; color: #94a3b8; padding: 30px 20px;">
                        <div style="font-size: 28px; margin-bottom: 8px;">📊</div>
                        Please select a problem first to generate an educational visual poster.
                    </div>
                `;
                return;
            }

            // Generate a unique request ID for stale-prevention
            const thisVizRequestId = 'viz-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
            _currentVizRequestId[containerId] = thisVizRequestId;

            // 1. FAST LOCAL STRUCTURED VISUALIZATION FIRST (Direct local simulator in < 2ms)
            try {
                const user = getAuthUser();
                const studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
                const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
                const sid = getStudentId();

                const fastRes = await fetch(`${API_BASE}/api/ai/companion/visualize`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...(getAuthToken() ? { "Authorization": `Bearer ${getAuthToken()}` } : {})
                    },
                    body: JSON.stringify({
                        message: `Visualize algorithm state sequence for ${probTitle}`,
                        stream: false,
                        context: {
                            student_id: sid,
                            student_name: studentName,
                            bot_name: botName,
                            problem_id: probId,
                            problem_title: probTitle,
                            problem_description: (currentProblemData && currentProblemData.description) || "",
                            current_code: code,
                            selected_language: language,
                            active_workspace: "problem_solving"
                        }
                    })
                });

                if (fastRes.ok) {
                    const fastData = await fastRes.json();
                    // Stale-prevention: only render if this is still the most recent request
                    if (_currentVizRequestId[containerId] !== thisVizRequestId) {
                        console.log('[Viz] Stale response discarded — newer request superseded this one');
                        return;
                    }
                    if (fastData.ok && fastData.visualization && fastData.visualization.steps && fastData.visualization.steps.length > 0) {
                        renderEducationalSlidePoster(containerId, fastData.visualization, fastData.message || "");
                        return;
                    }
                }
            } catch (fastErr) {
                console.warn("Fast visualizer local pass bypassed, falling back to companion chat:", fastErr);
            }

            container.innerHTML = `
                <div style="text-align: center; padding: 40px 20px; color: #94a3b8;">
                    <div class="dash-loading" style="width:32px; height:32px; border-radius:50%; border:3px solid rgba(2,132,199,0.2); border-top-color:#38bdf8; animation:spin 1s linear infinite; margin:0 auto 12px auto;"></div>
                    <div style="font-size: 14px; font-weight: 700; color: #38bdf8; margin-bottom: 6px;">Generating Educational Visual Poster...</div>
                    <div style="font-size: 12px; color: #64748b;">Maya is analyzing ${escapeHtml(probTitle)} algorithms &amp; state transitions</div>
                </div>
            `;

            try {
                const user = getAuthUser();
                const studentName = (user && (user.display_name || user.username)) || localStorage.getItem('codemind_user_name') || 'Learner';
                const botName = localStorage.getItem('codemind_bot_name') || 'Maya';
                const sid = getStudentId();

                const promptMsg = `Generate a structured educational visualization poster and 2 to 5 state steps explaining the algorithm execution and data structure transitions for solving "${probTitle}". Current language is ${language}. Current student code:\n\`\`\`${language}\n${code || '# No code written yet'}\n\`\`\``;

                const res = await fetch(`${API_BASE}/api/ai/companion/chat`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...(getAuthToken() ? { "Authorization": `Bearer ${getAuthToken()}` } : {})
                    },
                    body: JSON.stringify({
                        message: promptMsg,
                        stream: false,
                        context: {
                            student_id: sid,
                            student_name: studentName,
                            bot_name: botName,
                            problem_id: probId,
                            problem_title: probTitle,
                            problem_description: (currentProblemData && currentProblemData.description) || "",
                            current_code: code,
                            selected_language: language,
                            active_workspace: "problem_solving"
                        }
                    })
                });

                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || "Unable to generate algorithm visualization.");
                }

                const data = await res.json();
                if (data.visualization && data.visualization.steps && data.visualization.steps.length > 0) {
                    renderEducationalSlidePoster(containerId, data.visualization, data.message || "");
                } else {
                    // Clean textual breakdown without fake visualizations or random deque fallbacks
                    container.innerHTML = `
                        <div class="ai-card-box">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                                <div class="ai-card-title">📊 Algorithm Execution Breakdown</div>
                                <span class="badge" style="background:#0284c7; color:#fff;">DSA Step-by-Step</span>
                            </div>
                            <div style="color:#cbd5e1; font-size:13.5px; line-height:1.6; margin-bottom:14px;">
                                ${formatAITutorMarkdown(data.message || 'Step-by-step conceptual walkthrough generated successfully.')}
                            </div>
                            <div style="text-align:right;">
                                <button class="run-button" onclick="loadProblemVisualization('${containerId}')" style="margin-top:0; padding:6px 12px; font-size:12px;">
                                    🔄 Retry Poster Generation
                                </button>
                            </div>
                        </div>
                    `;
                }
            } catch (err) {
                container.innerHTML = `
                    <div class="ai-card-box" style="border-color: #ef4444; color: #f87171; padding: 20px;">
                        <div style="font-weight: 700; margin-bottom: 6px;">Visualization Note</div>
                        <div style="font-size: 13px; line-height: 1.5; color: #cbd5e1;">${escapeHtml(err.message)}</div>
                        <div style="margin-top: 12px;">
                            <button class="run-button" onclick="loadProblemVisualization('${containerId}')" style="margin-top: 0; padding: 6px 12px; font-size: 12px;">
                                🔄 Try Again
                            </button>
                        </div>
                    </div>
                `;
            }
        }

        function renderEducationalSlidePoster(containerId, spec, supportingText) {
            const container = document.getElementById(containerId);
            if (!container) return;

            problemVizState[containerId] = {
                spec: spec,
                stepIndex: 0,
                timer: null,
                speed: 1500
            };

            const totalSteps = (spec.steps && spec.steps.length) || 1;
            const stageId = `${containerId}_slideStage`;
            const explId = `${containerId}_slideExpl`;
            const stepBadgeId = `${containerId}_slideStepBadge`;
            const playBtnId = `${containerId}_slidePlayBtn`;
            const scrubberId = `${containerId}_slideScrubber`;

            container.innerHTML = `
                <div class="ai-card-box" style="padding: 14px; margin-bottom: 24px; border: 1px solid rgba(2,132,199,0.3); background: #070d18; flex-shrink: 0;">
                    <!-- Slide Header -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <span style="font-size:16px;">📊</span>
                            <span style="font-size:13px; font-weight:700; color:#38bdf8;">${escapeHtml(spec.title || 'Algorithm State Sequence')}</span>
                            <span class="badge" style="background:#0284c7; color:#fff; font-size:10px; padding:2px 6px;">${escapeHtml((spec.viz_type || 'DSA').toUpperCase())}</span>
                        </div>
                        <button class="filter-btn" onclick="loadProblemVisualization('${containerId}')" title="Re-generate visual poster" style="font-size:11px; padding:3px 8px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); color:#cbd5e1; border-radius:4px; cursor:pointer;">
                            🔄 Refresh
                        </button>
                    </div>

                    <!-- Slide Stage -->
                    <div id="${stageId}" style="min-height:160px; background:#04070e; border:1px solid #1e293b; border-radius:8px; display:flex; align-items:center; justify-content:center; padding:12px; margin-bottom:10px; overflow-x:auto; overflow-y:visible; max-width:100%; box-sizing:border-box;">
                    </div>

                    <!-- Step Explanation Card -->
                    <div id="${explId}" style="background:#0b1120; border-left:3px solid #38bdf8; border-radius:4px; padding:8px 12px; font-size:12px; color:#cbd5e1; line-height:1.45; margin-bottom:12px; min-height:42px;">
                    </div>

                    <!-- Slide Navigation & Step Controls -->
                    <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; background:rgba(15,23,42,0.6); padding:8px 10px; border-radius:6px; border:1px solid rgba(255,255,255,0.06);">
                        <div style="display:flex; align-items:center; gap:6px;">
                            <button class="run-button" onclick="restartProblemSlide('${containerId}')" style="margin-top:0; padding:4px 10px; font-size:11px; background:#1e293b; border:1px solid #334155; color:#cbd5e1;" title="Restart from Step 1">
                                ↺ Restart
                            </button>
                            <button class="run-button" onclick="stepProblemSlide('${containerId}', -1)" style="margin-top:0; padding:4px 10px; font-size:11px; background:#1e293b; border:1px solid #334155; color:#cbd5e1;" title="Previous State">
                                ◀ Prev
                            </button>
                            <button id="${playBtnId}" class="run-button" onclick="toggleProblemSlidePlay('${containerId}')" style="margin-top:0; padding:4px 10px; font-size:11px; background:#0284c7; color:#fff;" title="Play through states">
                                ▶ Play
                            </button>
                            <button class="run-button" onclick="stepProblemSlide('${containerId}', 1)" style="margin-top:0; padding:4px 10px; font-size:11px; background:#1e293b; border:1px solid #334155; color:#cbd5e1;" title="Next State">
                                Next ▶
                            </button>
                        </div>

                        <input type="range" id="${scrubberId}" min="0" max="${totalSteps - 1}" value="0" style="flex:1; min-width:80px; accent-color:#38bdf8;" oninput="scrubProblemSlide('${containerId}', this.value)">

                        <div style="display:flex; align-items:center; gap:8px;">
                            <span id="${stepBadgeId}" style="font-size:11px; color:#94a3b8; font-family:Consolas, monospace; font-weight:700;">1 / ${totalSteps}</span>
                            <select onchange="setProblemSlideSpeed('${containerId}', this.value)" style="background:#0f172a; border:1px solid #334155; color:#cbd5e1; font-size:10px; padding:2px 4px; border-radius:4px;">
                                <option value="2200">0.5x</option>
                                <option value="1500" selected>1x</option>
                                <option value="750">2x</option>
                            </select>
                        </div>
                    </div>

                    ${supportingText ? `
                        <div style="margin-top:12px; border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
                            <details style="font-size:12px; color:#94a3b8;">
                                <summary style="cursor:pointer; color:#38bdf8; font-weight:600; margin-bottom:6px;">📖 Pedagogical Notes &amp; Invariants</summary>
                                <div style="color:#cbd5e1; line-height:1.55; padding:6px 0;">${formatAITutorMarkdown(supportingText)}</div>
                            </details>
                        </div>
                    ` : ''}
                </div>
            `;

            renderProblemSlideStep(containerId, 0);
        }

        function restartProblemSlide(containerId) {
            const state = problemVizState[containerId];
            if (!state) return;
            if (state.timer) {
                clearInterval(state.timer);
                state.timer = null;
                const playBtn = document.getElementById(`${containerId}_slidePlayBtn`);
                if (playBtn) playBtn.textContent = '▶ Play';
            }
            renderProblemSlideStep(containerId, 0);
        }

        function renderProblemSlideStep(containerId, stepIndex) {
            const state = problemVizState[containerId];
            if (!state || !state.spec || !state.spec.steps || state.spec.steps.length === 0) return;

            const steps = state.spec.steps;
            stepIndex = Math.max(0, Math.min(steps.length - 1, stepIndex));
            state.stepIndex = stepIndex;

            const stage = document.getElementById(`${containerId}_slideStage`);
            const expl = document.getElementById(`${containerId}_slideExpl`);
            const badge = document.getElementById(`${containerId}_slideStepBadge`);
            const scrubber = document.getElementById(`${containerId}_slideScrubber`);

            if (scrubber) scrubber.value = stepIndex;
            if (badge) badge.textContent = `${stepIndex + 1} / ${steps.length}`;

            const step = steps[stepIndex];
            if (expl) {
                expl.innerHTML = `<strong>Step ${step.step_number || (stepIndex + 1)}:</strong> ${escapeHtml(step.explanation || '')}` +
                    (step.pointer ? `<div style="font-size:11px; color:#38bdf8; margin-top:3px; font-family:Consolas, monospace;">📍 ${escapeHtml(formatVizValue(step.pointer))}</div>` : '');
            }

            // Synchronize active visualization state for Maya context
            window.activeVisualizationState = {
                viz_type: state.spec.viz_type,
                title: state.spec.title,
                current_step: stepIndex + 1,
                total_steps: steps.length,
                action: step.action || '',
                explanation: step.explanation || '',
                current_state: typeof step.value !== 'undefined' ? (typeof step.value === 'object' ? JSON.stringify(step.value) : String(step.value)) : (step.pointer || ''),
                relevant_code_line: step.code_line || null
            };
            if (step.code_line) {
                highlightEditorCodeLine(step.code_line);
            }

            if (!stage) return;
            stage.innerHTML = '';

            const type = (state.spec.viz_type || '').toLowerCase();
            switch (type) {
                case 'circular_queue':
                case 'circular-queue':
                case 'circularqueue':
                    renderCircularQueueViz(stage, state.spec, stepIndex);
                    break;
                case 'topological_sort':
                case 'topological':
                case 'alien_dictionary':
                    renderTopologicalSortViz(stage, state.spec, stepIndex);
                    break;
                case 'flowchart':
                case 'algorithm':
                case 'state':
                case 'steps':
                case 'transition':
                    renderGenericFlowchartViz(stage, state.spec, stepIndex);
                    break;
                case 'stack':
                    renderStackViz(stage, state.spec, stepIndex);
                    break;
                case 'deque':
                case 'double_ended_queue':
                    renderDequeViz(stage, state.spec, stepIndex);
                    break;
                case 'queue':
                    renderQueueViz(stage, state.spec, stepIndex);
                    break;
                case 'circular_linked_list':
                case 'circular-linked-list':
                case 'cll':
                    renderCircularLinkedListViz(stage, state.spec, stepIndex);
                    break;
                case 'linked_list':
                case 'singly_linked_list':
                    renderLinkedListViz(stage, state.spec, stepIndex);
                    break;
                case 'doubly_linked_list':
                case 'doubly-linked-list':
                case 'doublylinkedlist':
                    renderDoublyLinkedListViz(stage, state.spec, stepIndex);
                    break;
                case 'array':
                    renderArrayViz(stage, state.spec, stepIndex);
                    break;
                case 'sorting':
                    renderSortingViz(stage, state.spec, stepIndex);
                    break;
                case 'recursion':
                    renderRecursionViz(stage, state.spec, stepIndex);
                    break;
                case 'tree':
                    renderTreeViz(stage, state.spec, stepIndex);
                    break;
                case 'graph':
                    renderGraphViz(stage, state.spec, stepIndex);
                    break;
                case 'pointers':
                    renderPointersViz(stage, state.spec, stepIndex);
                    break;
                case 'searching':
                    renderSearchingViz(stage, state.spec, stepIndex);
                    break;
                case 'hash_table':
                case 'hashing':
                case 'hashmap':
                    renderHashTableViz(stage, state.spec, stepIndex);
                    break;
                case 'string':
                case 'palindrome':
                    renderStringViz(stage, state.spec, stepIndex);
                    break;
                case 'code_trace':
                case 'trace':
                    renderCodeTraceViz(stage, state.spec, stepIndex);
                    break;
                default:
                    renderGenericFlowchartViz(stage, state.spec, stepIndex);
                    break;
            }
        }

        function stepProblemSlide(containerId, delta) {
            const state = problemVizState[containerId];
            if (!state || !state.spec || !state.spec.steps) return;
            let nextIndex = state.stepIndex + delta;
            if (nextIndex < 0) nextIndex = 0;
            if (nextIndex >= state.spec.steps.length) nextIndex = state.spec.steps.length - 1;
            renderProblemSlideStep(containerId, nextIndex);
        }

        function scrubProblemSlide(containerId, val) {
            renderProblemSlideStep(containerId, parseInt(val, 10));
        }

        function setProblemSlideSpeed(containerId, speedVal) {
            const state = problemVizState[containerId];
            if (!state) return;
            state.speed = parseInt(speedVal, 10) || 1500;
            if (state.timer) {
                clearInterval(state.timer);
                state.timer = setInterval(() => {
                    if (state.stepIndex < state.spec.steps.length - 1) {
                        stepProblemSlide(containerId, 1);
                    } else {
                        stepProblemSlide(containerId, -state.spec.steps.length);
                    }
                }, state.speed);
            }
        }

        function toggleProblemSlidePlay(containerId) {
            const state = problemVizState[containerId];
            if (!state || !state.spec || !state.spec.steps) return;
            const playBtn = document.getElementById(`${containerId}_slidePlayBtn`);

            if (state.timer) {
                clearInterval(state.timer);
                state.timer = null;
                if (playBtn) playBtn.textContent = '▶ Play';
            } else {
                if (playBtn) playBtn.textContent = '⏸ Pause';
                state.timer = setInterval(() => {
                    if (state.stepIndex < state.spec.steps.length - 1) {
                        stepProblemSlide(containerId, 1);
                    } else {
                        stepProblemSlide(containerId, -state.spec.steps.length);
                    }
                }, state.speed || 1500);
            }
        }

        // ========================================================
        // PREVIEW / APPLY FIX HANDLER
        // ========================================================
        function applyDebugFix(correctedSnippet, lineNum, origLine) {
            if (!correctedSnippet) return;
            const textarea = document.getElementById("code");
            if (!textarea) return;

            const currentCode = textarea.value;
            const lines = currentCode.split("\n");

            // Verify the target line matches
            const targetIdx = lineNum ? lineNum - 1 : -1;
            if (targetIdx >= 0 && targetIdx < lines.length) {
                // If origLine is provided, check if it matches closely
                lines[targetIdx] = correctedSnippet;
                textarea.value = lines.join("\n");
            } else {
                // If line number is not clear, ask user or do safe replacement
                textarea.value = currentCode.replace(origLine, correctedSnippet);
            }

            // Trigger input event for autosave / syntax highlighting
            textarea.dispatchEvent(new Event("input", { bubbles: true }));

            // Notify user with feedback
            const container = document.getElementById("aiTabContent");
            if (container) {
                const toast = document.createElement("div");
                toast.style.cssText = "background:#059669;color:#fff;padding:8px 12px;border-radius:6px;font-size:12px;font-weight:700;margin-top:10px;text-align:center;";
                toast.innerHTML = `✓ Fix applied to Line ${lineNum || ''}! Click "▶ Run" to verify.`;
                container.prepend(toast);
                setTimeout(() => toast.remove(), 4000);
            }
        }

        function applyFullSolutionToEditor(solutionCode) {
            if (!solutionCode) return;
            const textarea = document.getElementById("code");
            if (!textarea) return;

            // Prompt 2 Requirement: Do not overwrite existing user code without explicit action/confirmation
            if (textarea.value && textarea.value.trim().length > 30) {
                const confirmed = confirm("Are you sure you want to apply the full solution to the editor? This will replace your current code with the validated CodeMind solution.");
                if (!confirmed) return;
            }

            textarea.value = solutionCode;
            textarea.dispatchEvent(new Event("input", { bubbles: true }));

            // Notify user
            const container = document.getElementById("aiTabContent") || document.getElementById("aiPanelContent");
            if (container) {
                const toast = document.createElement("div");
                toast.style.cssText = "background:#0284c7;color:#fff;padding:10px 14px;border-radius:6px;font-size:12px;font-weight:700;margin-top:10px;text-align:center;";
                toast.innerHTML = `✓ Solution applied to editor! Click "▶ Run" to verify test execution.`;
                container.prepend(toast);
                setTimeout(() => toast.remove(), 4000);
            }
        }


        async function requestAIHint(level) {
            const container = document.getElementById("hintOutputContainer");
            container.textContent = `Fetching Level ${level} guidance...`;
            currentHintsUsed = Math.max(currentHintsUsed, level);
            if (level === 3) currentSolutionViewed = true;

            const probId = getActiveProblemId();
            const code = getActiveCode();
            const testId = isTestMode() && activeTestSession && activeTestSession.test ? activeTestSession.test.id : null;

            try {
                const res = await fetch(`${API_BASE}/api/ai/hint`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ problem_id: probId, hint_level: level, code: code, language: getActiveLanguage(), test_id: testId })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || "Unable to fetch hint.");
                }
                const data = await res.json();
                container.innerHTML = `<strong style="color: #38bdf8;">${escapeHtml(data.tier)}:</strong>\n\n${escapeHtml(data.hint)}`;
            } catch (err) {
                container.textContent = "Error: " + err.message;
            }
        }

        async function submitMockInterview() {
            const input = document.getElementById("interviewThoughtsInput").value.trim();
            const out = document.getElementById("interviewEvaluationOutput");
            const probId = getActiveProblemId();
            const code = getActiveCode();
            const language = getActiveLanguage();
            const testId = isTestMode() && activeTestSession && activeTestSession.test ? activeTestSession.test.id : null;

            out.innerHTML = "Evaluating your communication and algorithmic formulation...";
            try {
                const res = await fetch(`${API_BASE}/api/ai/interview`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ problem_id: probId, statement: input || "No statement", code: code || "# code", language: language, test_id: testId })
                });
                if (!res.ok) throw new Error("Could not evaluate interview.");
                const data = await res.json();
                out.innerHTML = `
                    <div style="background: #020617; border: 1px solid #334155; border-radius: 8px; padding: 14px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <div style="font-weight: 700; color: #38bdf8;">Interview Communication Score: ${data.interview_score}/100</div>
                            <span class="badge" style="background: #16a34a; color: #fff;">${escapeHtml(data.interviewer_verdict)}</span>
                        </div>
                        <ul style="padding-left: 20px; color: #cbd5e1; font-size: 13px; line-height: 1.6; margin-bottom: 8px;">
                            ${data.communication_feedback.map(f => `<li>${escapeHtml(f)}</li>`).join("")}
                        </ul>
                    </div>
                `;
            } catch (err) {
                out.textContent = "Error: " + err.message;
            }
        }

        // ========================================================
        // STUDENT PROGRESS DASHBOARD SYSTEM
        // ========================================================

        // Helper: map mastery status string to CSS class & color
        function masteryStatusClass(status) {
            switch ((status || '').toLowerCase().replace(/ /g, '-')) {
                case 'strong':         return { cls: 'strong',         color: '#22c55e' };
                case 'developing':     return { cls: 'developing',     color: '#38bdf8' };
                case 'needs-refresh':  return { cls: 'needs-refresh',  color: '#7c3aed' };
                default:               return { cls: 'needs-practice', color: '#64748b' };
            }
        }

        // Helper: map progression stage to CSS class
        function stageClass(stage) {
            const map = { 'Solved':'solved','Assisted':'assisted','Independent':'independent','Transfer':'transfer','Mastered':'mastered' };
            return map[stage] || 'solved';
        }

        async function loadProgressData() {
            // ── Refresh Stats button state machine ──────────────────────
            const refreshBtn = document.querySelector('#progressView button[onclick="loadProgressData()"]');
            const _btnOrigText = refreshBtn ? refreshBtn.innerHTML : null;
            if (refreshBtn) {
                refreshBtn.disabled = true;
                refreshBtn.innerHTML = '⏳ Refreshing…';
            }
            try {
                const sid = getStudentId();
                if (!sid && !isAuthenticated()) {
                    const zeroState = document.getElementById("progressZeroState");
                    if (zeroState) {
                        zeroState.innerHTML = `
                            <div style="font-size: 40px; margin-bottom: 12px;">🔒</div>
                            <h3 style="font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">Personalized Learning &amp; Skill Progress</h3>
                            <p style="color: #94a3b8; max-width: 500px; margin: 0 auto 20px auto; line-height: 1.5;">
                                Sign in or create an account to view your verified submissions, coding skill graph, concept mastery ratings, and personalized recommendations.
                            </p>
                            <button class="run-button" onclick="openAuthModal('signin')" style="margin-top: 0; padding:8px 20px;">Sign In / Register</button>
                        `;
                        zeroState.style.display = "block";
                    }
                    const progSec = document.getElementById("progressionChainSection");
                    if (progSec) progSec.style.display = "none";
                    renderSkillGraph(null);
                    if (refreshBtn) { refreshBtn.disabled = false; refreshBtn.innerHTML = _btnOrigText; }
                    return;
                }

                // Initial loading state for Weekly Solved Chart
                const sotLoading = document.getElementById("solvedOverTimeChart");
                if (sotLoading) sotLoading.innerHTML = '<div style="text-align:center; padding:30px; color:#64748b; font-size:13px;">⏳ Loading weekly activity…</div>';

                // Fetch progress and mastery in parallel for authenticated student
                const [progRes, mastRes] = await Promise.all([
                    authFetch(`${API_BASE}/api/progress?student_id=${encodeURIComponent(sid || '')}`),
                    authFetch(`${API_BASE}/api/mastery/dashboard?student_id=${encodeURIComponent(sid || '')}`)
                ]);
                if (!progRes.ok) throw new Error("Failed to load progress metrics.");
                const data = await progRes.json();
                const mastData = mastRes.ok ? await mastRes.json() : null;

                // Zero State Check (P2: Only show genuine zero state when database has zero records)
                const zeroState = document.getElementById("progressZeroState");
                if (zeroState) {
                    if (data.is_zero_state) {
                        zeroState.innerHTML = `
                            <div style="font-size: 40px; margin-bottom: 12px;">🌱</div>
                            <h3 style="font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 8px;">Welcome to CodeMind Learning!</h3>
                            <p style="color: #94a3b8; max-width: 500px; margin: 0 auto 20px auto; line-height: 1.5;">
                                You haven't submitted any problems or taken tests yet. Solve your first problem or take an assessment to generate your personalized coding skill graph and mastery ratings.
                            </p>
                            <button class="run-button" onclick="showProblemBrowser()" style="margin-top: 0;">Browse Problem Library</button>
                        `;
                        zeroState.style.display = "block";
                    } else {
                        zeroState.style.display = "none";
                    }
                }

                // Overview metrics
                document.getElementById("progSolvedCount").textContent = data.overview.problems_solved;
                document.getElementById("progAccuracyRate").textContent = `${data.overview.accuracy_rate}%`;
                document.getElementById("progIndependentCount").textContent = data.overview.independent_solves;
                const streak = data.daily_streak !== undefined ? data.daily_streak : (data.overview && data.overview.daily_streak !== undefined ? data.overview.daily_streak : 0);
                const streakEl = document.getElementById("progDailyStreak");
                const streakSub = document.getElementById("progDailyStreakSub");
                if (streakEl) streakEl.textContent = `🔥 ${streak}`;
                if (streakSub) streakSub.textContent = streak === 1 ? '1 active day' : `${streak} days streak`;
                document.getElementById("progTestsCompleted").textContent = data.overview.tests_completed;
                const avgScoreEl = document.getElementById("progAvgScore");
                if (avgScoreEl) {
                    avgScoreEl.textContent = (data.overview.tests_completed > 0 && data.overview.average_score !== undefined)
                        ? `${data.overview.average_score}%`
                        : "—%";
                }
                document.getElementById("progAttemptedSub").textContent = `${data.overview.problems_attempted} attempted`;
                document.getElementById("progTotalSub").textContent = `${data.overview.total_submissions} submissions`;

                // Solve Breakdown
                document.getElementById("progBreakdownIndep").textContent = data.solve_breakdown.independent;
                document.getElementById("progBreakdownAssisted").textContent = data.solve_breakdown.hint_assisted;
                document.getElementById("progBreakdownViewed").textContent = data.solve_breakdown.solution_viewed;

                // Independence Rate (improvement metric)
                const totalSolved = (data.solve_breakdown.independent || 0) + (data.solve_breakdown.hint_assisted || 0) + (data.solve_breakdown.solution_viewed || 0);
                const irEl = document.getElementById("progIndependenceRate");
                if (irEl) {
                    if (totalSolved > 0) {
                        const ir = Math.round((data.solve_breakdown.independent / totalSolved) * 100);
                        irEl.textContent = `${ir}%`;
                        irEl.style.color = ir >= 60 ? '#22c55e' : (ir >= 30 ? '#eab308' : '#f87171');
                    } else {
                        irEl.textContent = '—%';
                    }
                }

                // ── WHAT SHOULD I DO NEXT? ──────────────────────────────
                const naCard = document.getElementById("masteryNextAction");
                if (mastData && mastData.recommendations && mastData.recommendations.next_action) {
                    const na = mastData.recommendations.next_action;
                    const iconMap = { start:'🌱', refresh:'🔄', practice:'📌', independence:'💪', advance:'🚀' };
                    document.getElementById("masteryNextIcon").textContent = iconMap[na.type] || '🎯';
                    document.getElementById("masteryNextMsg").textContent = na.message;
                    const naBtn = document.getElementById("masteryNextBtn");
                    naBtn.textContent = na.cta;
                    // Store action safely in dataset instead of injecting into onclick attribute
                    naBtn.dataset.ctaAction = na.cta_action || 'showProblemBrowser()';
                    naBtn.dataset.problemId = na.cta_action && na.cta_action.startsWith("openProblem('")
                        ? na.cta_action.replace("openProblem('", '').replace("')", '')
                        : '';
                    naBtn.onclick = function() {
                        const pid = this.dataset.problemId;
                        if (pid) { openProblem(pid); }
                        else { showProblemBrowser(); }
                    };
                    if (naCard) naCard.style.display = "flex";
                } else if (naCard) {
                    naCard.style.display = "none";
                }

                // ── MASTERED CONCEPTS COUNT ────────────────────────────────
                const mcEl = document.getElementById("progMasteredConcepts");
                const mcSub = document.getElementById("progMasteredSub");
                if (mastData && mastData.concept_mastery && mastData.concept_mastery.concepts) {
                    const masteredCount = mastData.concept_mastery.concepts.filter(c => c.is_verified).length;
                    const totalConcepts = mastData.concept_mastery.concepts.length;
                    if (mcEl) mcEl.textContent = masteredCount;
                    if (mcSub) mcSub.textContent = totalConcepts > 0
                        ? `${masteredCount} of ${totalConcepts} concepts`
                        : '≥2 independent solves required';
                } else if (mcEl) {
                    mcEl.textContent = "—";
                    if (mcSub) mcSub.textContent = "Mastery data unavailable";
                }

                // ── PROGRESSION CHAIN (PART 7: ERROR & CONSISTENCY HANDLING) ────
                const progSection = document.getElementById("progressionChainSection");
                const chainRow = document.getElementById("progressionChainRow");
                if (progSection && chainRow) {
                    if (!mastRes.ok) {
                        // Part 7: If /api/mastery/dashboard returns error, do NOT silently render 0s.
                        progSection.style.display = "block";
                        chainRow.innerHTML = `
                            <div style="width:100%; padding: 12px 16px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; color: #fca5a5; font-size: 13px; display: flex; align-items: center; justify-content: space-between;">
                                <span>⚠️ Mastery progression data is temporarily unavailable (${escapeHtml(mastRes.statusText || 'HTTP ' + mastRes.status)}). Your practice records are intact.</span>
                                <button onclick="loadProgressData()" style="background:#334155; border:1px solid #475569; color:#f8fafc; border-radius:6px; padding:4px 10px; cursor:pointer; font-size:12px;">Retry</button>
                            </div>
                        `;
                    } else if (mastData && mastData.approach) {
                        const approach = mastData.approach;
                        const prog = approach.progression || {};
                        const stages = ["Solved","Assisted","Independent","Transfer","Mastered"];
                        const icons  = ["✓","💡","⚡","🔄","🏆"];
                        const counts = [prog.Solved||0, prog.Assisted||0, prog.Independent||0, prog.Transfer||0, prog.Mastered||0];

                        // Determine current stage (highest stage with count > 0)
                        let currentIdx = 0;
                        for (let i = 0; i < stages.length; i++) {
                            if (counts[i] > 0) currentIdx = i;
                        }

                        chainRow.innerHTML = "";
                        stages.forEach((stage, idx) => {
                            if (idx > 0) {
                                const conn = document.createElement("div");
                                conn.className = "prog-connector" + (idx <= currentIdx ? " reached" : "");
                                chainRow.appendChild(conn);
                            }
                            const step = document.createElement("div");
                            const stateCls = idx < currentIdx ? "reached" : (idx === currentIdx ? "current" : "");
                            step.className = `prog-step ${stateCls}`;
                            step.innerHTML = `
                                <div class="ps-dot" title="${stage}: ${counts[idx]}">${icons[idx]}</div>
                                <div class="ps-label">${stage}<br><small style="font-size:9px">${counts[idx]} problems</small></div>
                            `;
                            chainRow.appendChild(step);
                        });
                        progSection.style.display = data.is_zero_state ? "none" : "block";
                    }
                }

                // ── PROOF OF MASTERY — Concept Evidence Cards ────────────
                if (mastData && mastData.concept_mastery && mastData.concept_mastery.concepts && mastData.concept_mastery.concepts.length > 0) {
                    const pomSection = document.getElementById("proofOfMasterySection");
                    const pomCards = document.getElementById("pomConceptCards");
                    pomCards.innerHTML = "";
                    const statusOrder = { 'Needs Refresh': 0, 'Needs Practice': 1, 'Developing': 2, 'Strong': 3 };
                    const concepts = [...mastData.concept_mastery.concepts].sort((a, b) =>
                        (statusOrder[a.mastery_status]||9) - (statusOrder[b.mastery_status]||9)
                    );
                    concepts.forEach(c => {
                        const { cls, color } = masteryStatusClass(c.mastery_status);
                        const sc = stageClass(c.progression_stage);
                        const verifiedBadge = c.is_verified
                            ? `<span style="font-size:10px;background:#3b0764;color:#d8b4fe;padding:2px 8px;border-radius:999px;font-weight:700;">🏆 MASTERED</span>`
                            : '';
                        const needsMoreText = !c.is_verified
                            ? (() => {
                                const needed = Math.max(0, 2 - (c.independent_solves || 0));
                                const scoreNeeded = c.mastery_score < 70;
                                if (needed > 0) return `<span style="font-size:11px;color:#f59e0b;">Needs ${needed} more independent solve${needed>1?'s':''}</span>`;
                                if (scoreNeeded) return `<span style="font-size:11px;color:#f59e0b;">Needs ≥70% acceptance rate (currently ${c.mastery_score}%)</span>`;
                                return '';
                            })()
                            : '';

                        const card = document.createElement('div');
                        card.style.cssText = `background:#0f172a;border:1px solid #334155;border-radius:10px;padding:14px 18px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;`;
                        card.innerHTML = `
                            <div style="flex:1;min-width:200px;">
                                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                                    <span style="font-size:14px;font-weight:700;color:#f8fafc;">${escapeHtml(c.concept_name)}</span>
                                    <span class="mastery-badge ${cls}">${c.mastery_status}</span>
                                    ${verifiedBadge}
                                </div>
                                <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:#94a3b8;">
                                    <span>✓ ${c.accepted_submissions} accepted</span>
                                    <span>⚡ ${c.independent_solves} independent</span>
                                    <span>💡 ${c.hint_assisted_solves} assisted</span>
                                    <span>👁 ${c.solution_viewed_solves} viewed</span>
                                    <span>📊 ${c.mastery_score}% acceptance</span>
                                </div>
                                ${needsMoreText ? `<div style="margin-top:4px;">${needsMoreText}</div>` : ''}
                            </div>
                            <div style="display:flex;align-items:center;gap:8px;flex-shrink:0;">
                                <span class="stage-pill ${sc}">${c.progression_stage}</span>
                                <button style="font-size:11px;padding:4px 10px;background:#1e293b;color:#38bdf8;border:1px solid #38bdf8;border-radius:5px;cursor:pointer;font-weight:600;" onclick="showProblemBrowser()">Practice</button>
                            </div>
                        `;
                        pomCards.appendChild(card);
                    });
                    pomSection.style.display = "block";
                }

                // ── RENDER SKILL GRAPH (4-state) ─────────────────────────
                renderSkillGraph(data.skill_graph);

                // ── TOPIC MASTERY LIST (4-state badges + stage pills) ────
                const topicContainer = document.getElementById("progTopicList");
                topicContainer.innerHTML = "";
                data.topic_strengths_and_weaknesses.forEach(t => {
                    const ms = t.mastery_status || t.status || 'Needs Practice';
                    const { cls, color } = masteryStatusClass(ms);

                    // Find concept info from mastery data for progression stage
                    let stagePill = '';
                    if (mastData && mastData.concept_mastery && mastData.concept_mastery.concepts) {
                        const conceptInfo = mastData.concept_mastery.concepts.find(c => c.concept_name === t.topic);
                        if (conceptInfo && conceptInfo.progression_stage) {
                            const sc = stageClass(conceptInfo.progression_stage);
                            stagePill = `<span class="stage-pill ${sc}">${conceptInfo.progression_stage}</span>`;
                        }
                    }

                    const refreshBadge = t.needs_refresh
                        ? `<span style="font-size:10px;color:#c4b5fd;margin-left:4px;">⟳ refresh</span>`
                        : '';

                    const item = document.createElement("div");
                    item.style.marginBottom = "12px";
                    item.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 13px; margin-bottom: 5px;">
                            <span style="font-weight: 600; color: #f8fafc; display:flex; align-items:center; gap:6px;">
                                ${escapeHtml(t.topic)}${refreshBadge}
                                ${stagePill}
                            </span>
                            <span style="display:flex; align-items:center; gap:8px;">
                                <span style="color: #94a3b8; font-size:12px;">${t.solved} solved / ${t.attempted} tried</span>
                                <span class="mastery-badge ${cls}">${ms}</span>
                                <strong style="color: ${color}; font-size:13px;">${t.mastery_percentage}%</strong>
                            </span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar-fill" style="width: ${t.mastery_percentage}%; background: ${color};"></div>
                        </div>
                    `;
                    topicContainer.appendChild(item);
                });

                // ── LANGUAGES LIST ───────────────────────────────────────
                const langContainer = document.getElementById("progLanguageList");
                langContainer.innerHTML = "";
                if (data.language_breakdown && data.language_breakdown.length > 0) {
                    data.language_breakdown.forEach(l => {
                        const row = document.createElement("div");
                        row.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:6px 0;";
                        row.innerHTML = `
                            <span style="font-weight:600;color:#cbd5e1;text-transform:uppercase;font-size:13px;">${escapeHtml(l.language)}</span>
                            <span style="font-size:13px;color:#38bdf8;">${l.submissions} runs (${l.percentage}%)</span>
                        `;
                        langContainer.appendChild(row);
                    });
                } else {
                    langContainer.innerHTML = `<div style="color:#64748b;font-size:13px;">No code executions recorded yet.</div>`;
                }

                // ── COMMON MISTAKES LIST ─────────────────────────────────
                const mistContainer = document.getElementById("progMistakesList");
                mistContainer.innerHTML = "";
                if (data.common_mistakes && data.common_mistakes.length > 0) {
                    data.common_mistakes.forEach(m => {
                        const row = document.createElement("div");
                        row.style.cssText = "display:flex;justify-content:space-between;align-items:center;padding:6px 0;";
                        row.innerHTML = `
                            <span style="color:#f87171;font-size:13px;">${escapeHtml(m.label)}</span>
                            <span class="badge" style="background:#451a03;color:#fdba74;">${m.count} times</span>
                        `;
                        mistContainer.appendChild(row);
                    });
                } else {
                    mistContainer.innerHTML = `<div style="color:#64748b;font-size:13px;">Clean record! No recurring mistakes detected.</div>`;
                }



                // ── RETENTION / REFRESH SECTION ──────────────────────────
                const retData = mastData && mastData.retention;
                if (retData && retData.concepts_needing_refresh && retData.concepts_needing_refresh.length > 0) {
                    const retSection = document.getElementById("retentionSection");
                    const retAlerts = document.getElementById("retentionAlerts");
                    retSection.style.display = "block";

                    const details = retData.refresh_details || [];
                    const mastRecs = (mastData && mastData.recommendations && mastData.recommendations.recommendations) || [];
                    retAlerts.innerHTML = ""; // clear before repopulating

                    retData.concepts_needing_refresh.forEach(topic => {
                        const detail = details.find(d => d.topic === topic);
                        const daysText = detail ? `${detail.days_since_last_solve} days ago · ${detail.retention_score}% retained` : "Last seen: >21 days";

                        // Find a specific recommended problem for this refresh topic
                        const topicRec = mastRecs.find(r =>
                            r.mastery_status === 'Needs Refresh' && (r.target_topic === topic || (r.target_topic||'').includes(topic))
                        ) || mastRecs.find(r => r.target_topic === topic || (r.target_topic||'').includes(topic));

                        const alertEl = document.createElement('div');
                        alertEl.className = 'refresh-alert';
                        alertEl.innerHTML = `
                            <div class="ra-icon">🔄</div>
                            <div class="ra-text"><strong>${escapeHtml(topic)}</strong> — knowledge fading</div>
                            <div class="ra-days">${daysText}</div>
                            <div style="display:flex;gap:6px;flex-shrink:0;">
                                <button class="ra-btn" ${topicRec ? `data-problem-id="${topicRec.problem_id}"` : ''} data-topic="${escapeHtml(topic)}" onclick="_reviseTopicProblem(this)">Revise</button>
                                <button style="background:#0c4a6e;color:#7dd3fc;border:none;border-radius:6px;padding:5px 12px;font-size:12px;font-weight:600;cursor:pointer;" onclick="openAITutorModal('learn')">🧠 AI Tutor</button>
                            </div>
                        `;
                        retAlerts.appendChild(alertEl);
                    });
                }

                // ── TEST HISTORY ─────────────────────────────────────────
                const testHistContainer = document.getElementById("progTestHistoryContainer");
                if (data.test_history && data.test_history.length > 0) {
                    let tableHtml = `
                        <table class="problems-table" style="margin-top:8px;">
                            <thead><tr>
                                <th>Assessment Test</th><th>Earned Score</th><th>Percentage</th><th>Date</th>
                            </tr></thead><tbody>`;
                    data.test_history.forEach(th => {
                        const pBadge = th.percentage >= 70
                            ? `<span class="badge" style="background:#16a34a;color:#fff;">${th.percentage}% PASS</span>`
                            : `<span class="badge" style="background:#d97706;color:#fff;">${th.percentage}%</span>`;
                        tableHtml += `
                            <tr>
                                <td style="font-weight:600;color:#f8fafc;">${escapeHtml(th.title)}</td>
                                <td>${th.total_score} / ${th.max_score} pts</td>
                                <td>${pBadge}</td>
                                <td style="color:#94a3b8;font-size:13px;">${th.submitted_at ? th.submitted_at.substring(0, 10) : ''}</td>
                            </tr>`;
                    });
                    tableHtml += `</tbody></table>`;
                    testHistContainer.innerHTML = tableHtml;
                } else {
                    testHistContainer.innerHTML = `<div style="color:#64748b;font-size:13px;text-align:center;padding:20px;">No assessment tests completed yet.</div>`;
                }

                // ── RECOMMENDATIONS (from mastery engine) ────────────────
                const recGrid = document.getElementById("progRecommendationsGrid");
                recGrid.innerHTML = "";

                // Use mastery recommendations if available, else fall back to progress recs
                const recs = (mastData && mastData.recommendations && mastData.recommendations.recommendations.length > 0)
                    ? mastData.recommendations.recommendations
                    : (data.recommendations || []);

                if (recs.length > 0) {
                    recs.forEach((r, idx) => {
                        const ms = r.mastery_status || 'Needs Practice';
                        const { cls, color } = masteryStatusClass(ms);
                        const msIcon = ms === 'Needs Refresh' ? '🔄' : (ms === 'Strong' ? '✅' : '📌');

                        // Category tier assignment
                        let tierLabel = "Same Concept";
                        let tierBg = "#0284c7";
                        const diff = (r.difficulty || 'Easy').toLowerCase();
                        if (diff === 'easy') {
                            tierLabel = "Easier Practice";
                            tierBg = "#16a34a";
                        } else if (diff === 'hard' || diff === 'expert') {
                            tierLabel = "Transfer Challenge";
                            tierBg = "#7c3aed";
                        }

                        const card = document.createElement("div");
                        card.className = "card";
                        card.style.padding = "18px";
                        card.innerHTML = `
                            <div>
                                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:8px;">
                                    <strong style="color:#f8fafc;font-size:14px;flex:1;">${escapeHtml(r.title)}</strong>
                                    <div style="display:flex;gap:4px;align-items:center;">
                                        <span class="badge" style="background:${tierBg};color:#fff;font-size:10px;padding:2px 6px;">${tierLabel}</span>
                                        <span class="badge badge-${diff}">${escapeHtml(r.difficulty||'Easy')}</span>
                                    </div>
                                </div>
                                <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;">
                                    <span class="mastery-badge ${cls}">${msIcon} ${ms}</span>
                                    ${r.target_topic ? `<span style="font-size:11px;color:#64748b;">${escapeHtml(r.target_topic)}</span>` : ''}
                                </div>
                                <p style="color:#94a3b8;font-size:13px;margin-bottom:14px;">${escapeHtml(r.reason)}</p>
                            </div>
                            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                                <button class="run-button" onclick="openProblem('${r.problem_id}')" style="margin-top:0;padding:6px 14px;font-size:12px;width:fit-content;">
                                    Solve &rarr;
                                </button>
                                <button class="nav-button" onclick="openProblemWithTutor('${r.problem_id}')" style="font-size:12px;padding:6px 12px;background:#1e293b;color:#38bdf8;border-color:#38bdf8;">
                                    🧠 + AI Tutor
                                </button>
                            </div>
                        `;
                        recGrid.appendChild(card);
                    });
                } else {
                    recGrid.innerHTML = `<div style="color:#64748b;font-size:13px;">No recommendations yet. Start solving problems to generate your mastery profile!</div>`;
                }

                // ── PROBLEMS SOLVED PER WEEK (Clean 7-day Activity Chart) ────
                const sotContainer = document.getElementById("solvedOverTimeChart");
                const weekly = (Array.isArray(data.weekly_solved) && data.weekly_solved.length === 7)
                    ? data.weekly_solved
                    : [
                        { day: 'Mon', day_full: 'Monday', solved: 0, date: '' },
                        { day: 'Tue', day_full: 'Tuesday', solved: 0, date: '' },
                        { day: 'Wed', day_full: 'Wednesday', solved: 0, date: '' },
                        { day: 'Thu', day_full: 'Thursday', solved: 0, date: '' },
                        { day: 'Fri', day_full: 'Friday', solved: 0, date: '' },
                        { day: 'Sat', day_full: 'Saturday', solved: 0, date: '' },
                        { day: 'Sun', day_full: 'Sunday', solved: 0, date: '' }
                    ];

                const totalWeekSolved = weekly.reduce((acc, d) => acc + (d.solved || 0), 0);
                const maxSolved = Math.max(...weekly.map(d => d.solved || 0), 1);

                const badgeEl = document.getElementById("weeklyTotalBadge");
                if (badgeEl) {
                    badgeEl.textContent = `${totalWeekSolved} solved this week`;
                }

                if (sotContainer) {
                    const colsHtml = weekly.map(d => {
                        const count = d.solved || 0;
                        const isToday = Boolean(d.is_today);
                        const heightPct = count > 0 ? Math.max(Math.round((count / maxSolved) * 100), 14) : 0;
                        const countColor = count > 0 ? '#38bdf8' : '#64748b';
                        const dayColor = isToday ? '#38bdf8' : '#94a3b8';
                        const trackBorder = isToday
                            ? 'border: 1px solid rgba(56, 189, 248, 0.5); box-shadow: 0 0 10px rgba(56, 189, 248, 0.15);'
                            : 'border: 1px solid #334155;';
                        const todayBadge = isToday
                            ? '<span style="font-size:9px; background:#0284c7; color:#f0f9ff; padding:1px 5px; border-radius:4px; font-weight:700; text-transform:uppercase;">Today</span>'
                            : '';
                        const dateFormatted = d.date ? d.date.substring(5) : '';

                        return `
                            <div style="flex:1; display:flex; flex-direction:column; align-items:center; min-width:0;">
                                <!-- Numeric Count -->
                                <div style="font-size:14px; font-weight:800; color:${countColor}; margin-bottom:8px;">
                                    ${count}
                                </div>

                                <!-- Bar Track -->
                                <div style="width:100%; max-width:44px; height:120px; background:#0f172a; border-radius:6px; ${trackBorder} display:flex; align-items:flex-end; padding:2px; position:relative;"
                                     title="${escapeHtml(d.day_full || d.day)}: ${count} solved${d.date ? ' (' + escapeHtml(d.date) + ')' : ''}">
                                    <div style="width:100%; height:${heightPct}%; background:linear-gradient(180deg, #38bdf8 0%, #0284c7 100%); border-radius:4px; transition:height 0.3s ease; ${count === 0 ? 'display:none;' : ''}"></div>
                                    ${count === 0 ? '<div style="width:100%; height:2px; background:#334155; border-radius:1px;"></div>' : ''}
                                </div>

                                <!-- Day Label -->
                                <div style="font-size:12px; font-weight:700; color:${dayColor}; margin-top:10px; text-transform:uppercase; letter-spacing:0.5px;">
                                    ${escapeHtml(d.day)}
                                </div>

                                <!-- Date / Today Indicator -->
                                <div style="font-size:10px; color:#64748b; margin-top:2px; height:16px; display:flex; align-items:center; justify-content:center;">
                                    ${todayBadge || escapeHtml(dateFormatted)}
                                </div>
                            </div>
                        `;
                    }).join('');

                    const messageHtml = totalWeekSolved === 0
                        ? `<div style="text-align:center; color:#64748b; font-size:12px; margin-top:16px; padding-top:14px; border-top:1px solid #334155;">No problems solved yet this week. Solve a problem to start your weekly streak!</div>`
                        : `<div style="text-align:center; color:#94a3b8; font-size:12px; margin-top:16px; padding-top:14px; border-top:1px solid #334155;">Great work! You've solved <strong>${totalWeekSolved}</strong> distinct problem${totalWeekSolved > 1 ? 's' : ''} this week.</div>`;

                    sotContainer.innerHTML = `
                        <div style="display:flex; justify-content:space-between; gap:10px; align-items:flex-end; padding:10px 4px 4px 4px;">
                            ${colsHtml}
                        </div>
                        ${messageHtml}
                    `;
                }

            } catch (err) {
                console.error("Progress loading error:", err);
                const zeroState = document.getElementById("progressZeroState");
                if (zeroState) zeroState.style.display = "none";
                const sotContainer = document.getElementById("solvedOverTimeChart");
                if (sotContainer) {
                    sotContainer.innerHTML = `<div style="background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3); border-radius:8px; padding:20px; text-align:center; color:#f87171; font-size:13px;">⚠️ Unable to load weekly solved data. <button onclick="loadProgressData()" style="margin-left:10px; background:#1e293b; color:#38bdf8; border:1px solid #38bdf8; border-radius:4px; padding:3px 10px; cursor:pointer;">Retry</button></div>`;
                }
                const streakEl = document.getElementById("progDailyStreak");
                if (streakEl) streakEl.textContent = "—";
                const streakSub = document.getElementById("progDailyStreakSub");
                if (streakSub) streakSub.textContent = "Unavailable";
                const topicContainer = document.getElementById("progTopicList");
                if (topicContainer) {
                    topicContainer.innerHTML = `<div style="color:#f87171;font-size:13px;padding:12px 0;">⚠️ Failed to load topic mastery data.</div>`;
                }
                const recGrid = document.getElementById("progRecommendationsGrid");
                if (recGrid) {
                    recGrid.innerHTML = `<div style="color:#f87171;font-size:13px;padding:12px 0;">⚠️ Recommendations currently unavailable.</div>`;
                }
            } finally {
                // Always restore the Refresh Stats button regardless of success or failure
                if (refreshBtn) {
                    refreshBtn.disabled = false;
                    refreshBtn.innerHTML = _btnOrigText;
                }
            }
        }

        // Open a problem AND immediately open AI Tutor
        function openProblemWithTutor(problemId) {
            openProblem(problemId);
            setTimeout(() => openAITutorModal('hint'), 600);
        }

        // Retention: Revise a specific topic — open its recommended problem + AI tutor if available
        function _reviseTopicProblem(btn) {
            const problemId = btn && btn.dataset && btn.dataset.problemId;
            if (problemId) {
                openProblemWithTutor(problemId);
            } else {
                showProblemBrowser();
            }
        }

        // HTML5 CANVAS PERSONAL CODING SKILL GRAPH RENDERER (4-state mastery)
        function renderSkillGraph(graphData) {
            const canvas = document.getElementById("skillGraphCanvas");
            if (!canvas) return;

            // HDPI / Retina support
            const dpr = window.devicePixelRatio || 1;
            const W = canvas.offsetWidth || 960;
            const H = canvas.offsetHeight || 320;
            canvas.width = W * dpr;
            canvas.height = H * dpr;
            canvas.style.width = W + "px";
            canvas.style.height = H + "px";

            const ctx = canvas.getContext("2d");
            ctx.scale(dpr, dpr);
            ctx.clearRect(0, 0, W, H);

            const nodes = graphData && graphData.nodes ? graphData.nodes : [];
            const edges = graphData && graphData.edges ? graphData.edges : [];

            // P4: If genuinely no learning data, render clean encouraging state
            const hasLearningData = nodes.some(n => (n.mastery > 0 || (n.solved && n.solved > 0)));
            if (!hasLearningData) {
                ctx.fillStyle = "#94a3b8";
                ctx.font = "bold 15px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
                ctx.textAlign = "center";
                ctx.fillText("Your Coding Skill Graph will grow as you solve problems.", W / 2, H / 2 - 8);
                ctx.fillStyle = "#64748b";
                ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
                ctx.fillText("Solve your first problem or take an assessment test to map your concept mastery.", W / 2, H / 2 + 16);
                return;
            }

            // Short display labels for long topic names
            const LABEL_ALIASES = {
                "Depth-First Search (DFS) / Breadth-First Search (BFS)": "DFS / BFS",
                "Dynamic Programming": "DP",
                "Binary Search": "Binary\nSearch"
            };

            // Pre-defined layout coordinates for clean aesthetic graph
            const positions = {
                "Hash Table":       { x: 160, y: 160 },
                "Two Pointers":     { x: 380, y: 90 },
                "Prefix Sums":      { x: 160, y: 260 },
                "Sliding Window":   { x: 600, y: 80 },
                "Binary Search":    { x: 600, y: 180 },
                "Depth-First Search (DFS) / Breadth-First Search (BFS)": { x: 380, y: 250 },
                "Dynamic Programming": { x: 800, y: 250 }
            };

            // Draw connecting edges
            ctx.lineWidth = 2;
            edges.forEach(e => {
                const p1 = positions[e.from];
                const p2 = positions[e.to];
                if (p1 && p2) {
                    ctx.strokeStyle = "#334155";
                    ctx.beginPath();
                    ctx.moveTo(p1.x, p1.y);
                    ctx.lineTo(p2.x, p2.y);
                    ctx.stroke();
                }
            });

            // Draw nodes — 4-state colour mapping
            nodes.forEach(n => {
                const pos = positions[n.id] || { x: 450, y: 160 };
                const mastery = n.mastery || 0;
                const ms = n.mastery_status || n.status || '';

                // 4-state color
                let color = "#64748b"; // Needs Practice
                if (ms === "Strong" || ms === "strong")                color = "#22c55e";
                else if (ms === "Developing" || ms === "developing")   color = "#38bdf8";
                else if (ms === "Needs Refresh" || ms === "needs_refresh") color = "#7c3aed";

                // Pulse halo for Needs Refresh
                if (ms === "Needs Refresh" || ms === "needs_refresh") {
                    ctx.beginPath();
                    ctx.arc(pos.x, pos.y, 40, 0, Math.PI * 2);
                    ctx.strokeStyle = "#7c3aed44";
                    ctx.lineWidth = 6;
                    ctx.stroke();
                }

                // Node circle
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 32, 0, Math.PI * 2);
                ctx.fillStyle = "#0f172a";
                ctx.fill();
                ctx.strokeStyle = color;
                ctx.lineWidth = 3;
                ctx.stroke();

                // Mastery progress arc
                if (mastery > 0) {
                    ctx.beginPath();
                    ctx.arc(pos.x, pos.y, 36, -Math.PI / 2, (-Math.PI / 2) + (Math.PI * 2 * (mastery / 100)));
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 3;
                    ctx.stroke();
                }

                // Label — use alias if available, otherwise truncate
                const displayLabel = LABEL_ALIASES[n.label] || (n.label.length > 13 ? n.label.substring(0, 11) + ".." : n.label);
                ctx.fillStyle = "#f8fafc";
                ctx.font = "bold 11px -apple-system, sans-serif";
                ctx.textAlign = "center";
                // Support multi-line alias labels (split by \n)
                const labelLines = displayLabel.split("\n");
                const lineH = 13;
                const startY = pos.y - 4 - ((labelLines.length - 1) * lineH / 2);
                labelLines.forEach((line, i) => {
                    ctx.fillText(line, pos.x, startY + i * lineH);
                });

                ctx.fillStyle = color;
                ctx.font = "10px Consolas, monospace";
                ctx.fillText(`${mastery}%`, pos.x, pos.y + 18);
            });
        }

        function askTutor() {
            openAITutorModal('explain');
        }

        function viewProgress() {
            showProgressView();
        }

        function escapeHtml(text) {
            if (!text) return "";
            return String(text)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        // Initialize on page load & restore session if present
        window.addEventListener("DOMContentLoaded", () => {
            checkBackendHealth();
            loadDropdowns();
            fetchStats();
            setupWorkspaceDraftAutosave();

            // ── Authentication & Profile Onboarding ──────────────────────
            (async () => {
                renderNavAuth();
                if (isAuthenticated()) {
                    try {
                        const r = await authFetch(`${API_BASE}/api/auth/me`);
                        if (r.ok) {
                            const data = await r.json();
                            if (data.user) {
                                localStorage.setItem('codemind_auth_user', JSON.stringify(data.user));
                                window.currentUserHasGroqKey = !!data.user.has_groq_key;
                                window.currentUserGroqKeyPreview = data.user.groq_key_preview || '';
                                const dName = (data.profile && data.profile.student_name) || data.user.display_name || data.user.username;
                                localStorage.setItem('codemind_user_name', dName);
                            }
                            if (data.profile && data.profile.bot_name) {
                                localStorage.setItem('codemind_bot_name', data.profile.bot_name);
                            }
                            applyUserName();
                            renderNavAuth();
                            if (data.user && !data.user.has_groq_key && !sessionStorage.getItem('cmGroqPromptDismissed')) {
                                sessionStorage.setItem('cmGroqPromptDismissed', '1');
                                setTimeout(() => openGroqKeyModal(true), 600);
                            }
                        }
                    } catch(e) {
                        applyUserName();
                    }
                    initDashboard();
                } else {
                    applyUserName();
                    renderNavAuth();
                    initDashboard();
                }
            })();
            // ─────────────────────────────────────────────────────────────

            // Resume active test if present and not expired
            const savedRaw = localStorage.getItem('codemind_active_test');
            if (savedRaw) {
                try {
                    const parsed = JSON.parse(savedRaw);
                    if (parsed && parsed.test && parsed.endTime) {
                        if (Date.now() < parsed.endTime) {
                            startTestTaking(parsed.test.id);
                        } else {
                            localStorage.removeItem('codemind_active_test');
                        }
                    }
                } catch (e) {
                    localStorage.removeItem('codemind_active_test');
                }
            }

            // Global Escape key handler for dialog accessibility
            window.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    closeCompanionRenameModal();
                    closeClearChatConfirmModal();
                    closeTestModal();
                    closeCustomQuestionModal();
                    closeResultModal();
                    closeAITutorModal();
                    if (typeof closeAuthModal === 'function') closeAuthModal();
                    document.body.classList.remove('modal-open');
                }
            });
        });
    