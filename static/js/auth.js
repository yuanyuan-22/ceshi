// =========================
// JWT 自动检测
// =========================

const INACTIVITY_TIMEOUT = 10 * 60 * 1000; // 10分钟未操作自动登出

function getToken() {
    return localStorage.getItem("jwt_access");
}

function getRefreshToken() {
    return localStorage.getItem("jwt_refresh");
}

// 检查是否登录
function requireLogin() {
    const token = getToken();

    if (!token) {
        alert("请先登录");
        window.location.href = "/";
        throw new Error("No JWT Token");
    }

    // 启动 inactivity timer
    startInactivityTimer();

    return token;
}

// =========================
// Inactivity Timer - 10分钟未操作自动登出
// =========================
let inactivityTimer = null;
let lastActivity = Date.now();

function resetInactivityTimer() {
    lastActivity = Date.now();
}

function startInactivityTimer() {
    // 清除之前的 timer
    if (inactivityTimer) {
        clearTimeout(inactivityTimer);
    }

    // 监听用户活动
    const events = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'];
    events.forEach(event => {
        document.addEventListener(event, resetInactivityTimer, { passive: true });
    });

    // 每分钟检查一次
    inactivityTimer = setInterval(checkInactivity, 60 * 1000);
}

function checkInactivity() {
    const elapsed = Date.now() - lastActivity;
    if (elapsed >= INACTIVITY_TIMEOUT) {
        logout(true); // true 表示是自动登出
    }
}

function logout(isAuto = false) {
    localStorage.removeItem("jwt_access");
    localStorage.removeItem("jwt_refresh");

    if (inactivityTimer) {
        clearTimeout(inactivityTimer);
        inactivityTimer = null;
    }

    if (isAuto) {
        alert("由于长时间未操作，您已自动登出");
    }
    window.location.href = "/";
}

// =========================
// 刷新 token
// =========================
async function refreshToken() {
    const refresh = getRefreshToken();

    if (!refresh) {
        logout();
        throw new Error("No refresh token");
    }

    const res = await fetch("/api/auth/refresh/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ refresh: refresh })
    });

    if (!res.ok) {
        logout();
        throw new Error("Refresh token failed");
    }

    const data = await res.json();
    localStorage.setItem("jwt_access", data.access);
    resetInactivityTimer(); // 刷新 token 后重置 timer
    return data.access;
}

// =========================
// 自动带 JWT 的 fetch
// =========================

async function authFetch(url, options = {}) {
    let token = getToken();

    options = options || {};
    options.headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${token}`
    };

    let res = await fetch(url, options);

    if (res.status === 401) {
        try {
            token = await refreshToken();
            options.headers.Authorization = `Bearer ${token}`;
            res = await fetch(url, options);
        } catch (e) {
            // refreshToken 失败会调用 logout()
            throw e;
        }
    }

    return res;
}