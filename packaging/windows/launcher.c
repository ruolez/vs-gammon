/* VS Gammon for Windows: starts the bundled server (python\python.exe -m app.desktop) and shows it in a window of
 * its own with two WebView2 views: the app, and on the Play online page the game site laid over the page's
 * placeholder (sites like BackgammonGalaxy refuse to be shown in an iframe). The window opens on starting.html,
 * which switches to the app once the server answers. Closing the window closes the server's stdin, which stops it.
 * Without the WebView2 runtime the app opens in the default browser instead. */
#define _WIN32_WINNT 0x0A00
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <winsock2.h>
#include <shellapi.h>
#include <dwmapi.h>
#include <wincrypt.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "WebView2.h"

#define PORT 5565
#define URL L"http://127.0.0.1:5565/"
#define START_TIMEOUT_MS 150000
#define WINDOW_CLASS L"VSGammonWindow"
#define PLAY_CLASS L"VSGammonPlay"
#define TEXT_MAX 4096

static wchar_t app_dir[MAX_PATH];
static wchar_t data_dir[MAX_PATH];
static HWND window, play_host;
static HANDLE server_process;
static int server_up, open_in_browser;
static DWORD started_at;

static ICoreWebView2Environment *environment;
static ICoreWebView2Controller *main_controller, *play_controller;
static ICoreWebView2 *main_view, *play_view;
static int play_creating, play_loading;
static wchar_t play_pending[TEXT_MAX];

static void fail(const wchar_t *message) {
    wchar_t text[1024];
    swprintf(text, 1024, L"%ls\n\nDetails are in %ls\\server.log", message, data_dir);
    MessageBoxW(window, text, L"VS Gammon", MB_ICONERROR | MB_OK);
    ExitProcess(1);
}

static int server_ready(void) {
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return 0;
    struct sockaddr_in addr = {0};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(PORT);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    DWORD timeout = 2000;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&timeout, sizeof timeout);
    int ok = 0;
    if (connect(s, (struct sockaddr *)&addr, sizeof addr) == 0) {
        const char request[] = "GET /health HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n";
        char reply[64] = {0};
        if (send(s, request, (int)sizeof request - 1, 0) > 0 && recv(s, reply, (int)sizeof reply - 1, 0) > 0)
            ok = strstr(reply, " 200 ") != NULL;
    }
    closesocket(s);
    return ok;
}

static void starting_page_url(wchar_t *url, size_t size) {
    wchar_t path[MAX_PATH];
    char utf8[4 * MAX_PATH];
    swprintf(path, MAX_PATH, L"%ls\\starting.html", app_dir);
    WideCharToMultiByte(CP_UTF8, 0, path, -1, utf8, sizeof utf8, NULL, NULL);
    size_t n = (size_t)swprintf(url, size, L"file:///");
    for (const unsigned char *c = (const unsigned char *)utf8; *c && n + 4 < size; c++) {
        if (*c == '\\') url[n++] = L'/';
        else if ((*c >= 'A' && *c <= 'Z') || (*c >= 'a' && *c <= 'z') || (*c >= '0' && *c <= '9') || strchr("-._~/:", *c))
            url[n++] = *c;
        else n += (size_t)swprintf(url + n, size - n, L"%%%02X", *c);
    }
    url[n] = 0;
}

static void show_in_browser(void) {
    ShellExecuteW(NULL, L"open", URL, NULL, NULL, SW_SHOWNORMAL);
    MessageBoxW(NULL, L"VS Gammon is open in your browser.\n\nClick OK to quit VS Gammon.", L"VS Gammon",
                MB_ICONINFORMATION | MB_OK);
}

static int starts_with(const wchar_t *text, const wchar_t *prefix) { return text && wcsncmp(text, prefix, wcslen(prefix)) == 0; }

static int is_web(const wchar_t *uri) { return starts_with(uri, L"http://") || starts_with(uri, L"https://"); }

/* ---------- the little JSON the page sends: {"id":1,"name":"play","args":{"action":"frame","rect":{...},...}} ---------- */

static const wchar_t *json_value(const wchar_t *json, const wchar_t *key) {
    wchar_t pattern[64];
    swprintf(pattern, 64, L"\"%ls\":", key);
    for (const wchar_t *at = wcsstr(json, pattern); at; at = wcsstr(at + 1, pattern))
        if (at == json || at[-1] != L'\\') return at + wcslen(pattern);
    return NULL;
}

static double json_number(const wchar_t *json, const wchar_t *key, double fallback) {
    const wchar_t *at = json_value(json, key);
    return at ? wcstod(at, NULL) : fallback;
}

static int json_string(const wchar_t *json, const wchar_t *key, wchar_t *out, size_t size) {
    const wchar_t *at = json_value(json, key);
    size_t n = 0;
    out[0] = 0;
    if (!at || *at != L'"') return 0;
    for (at++; *at && *at != L'"' && n + 1 < size; at++) {
        if (*at != L'\\') { out[n++] = *at; continue; }
        switch (*++at) {
            case L'n': out[n++] = L'\n'; break;
            case L't': out[n++] = L'\t'; break;
            case L'r': out[n++] = L'\r'; break;
            case L'b': out[n++] = L'\b'; break;
            case L'f': out[n++] = L'\f'; break;
            case L'u': {
                wchar_t hex[5] = {0};
                for (int i = 0; i < 4 && at[1]; i++) hex[i] = *++at;
                out[n++] = (wchar_t)wcstoul(hex, NULL, 16);
                break;
            }
            case 0: at--; break;
            default: out[n++] = *at;
        }
    }
    out[n] = 0;
    return 1;
}

static void json_escape(const wchar_t *in, wchar_t *out, size_t size) {
    size_t n = 0;
    for (; in && *in && n + 7 < size; in++) {
        if (*in == L'"' || *in == L'\\') { out[n++] = L'\\'; out[n++] = *in; }
        else if (*in < 0x20) n += (size_t)swprintf(out + n, size - n, L"\\u%04x", *in);
        else out[n++] = *in;
    }
    out[n] = 0;
}

/* ---------- COM callback objects: one static object per callback ---------- */

typedef struct { void *vtbl; const IID *iid; } Handler;

static HRESULT STDMETHODCALLTYPE handler_query(Handler *self, REFIID riid, void **out) {
    if (IsEqualIID(riid, &IID_IUnknown) || IsEqualIID(riid, self->iid)) { *out = self; return S_OK; }
    *out = NULL;
    return E_NOINTERFACE;
}

static ULONG STDMETHODCALLTYPE handler_ref(Handler *self) { (void)self; return 1; }

#define HANDLER(name, iface, invoke) \
    static iface##Vtbl name##_vtbl = {(void *)handler_query, (void *)handler_ref, (void *)handler_ref, invoke}; \
    static Handler name = {&name##_vtbl, &IID_##iface};
#define AS(iface, handler) ((iface *)&(handler))

/* ---------- the game view ---------- */

static void play_state_json(wchar_t *out, size_t size) {
    LPWSTR source = NULL, title = NULL;
    BOOL back = FALSE, forward = FALSE;
    if (play_view) {
        ICoreWebView2_get_Source(play_view, &source);
        ICoreWebView2_get_DocumentTitle(play_view, &title);
        ICoreWebView2_get_CanGoBack(play_view, &back);
        ICoreWebView2_get_CanGoForward(play_view, &forward);
    }
    static wchar_t url[TEXT_MAX], name[1024];
    json_escape(source && is_web(source) ? source : play_pending, url, TEXT_MAX);
    json_escape(title, name, 1024);
    swprintf(out, size, L"{\"url\":\"%ls\",\"title\":\"%ls\",\"loading\":%ls,\"canGoBack\":%ls,\"canGoForward\":%ls}", url, name,
             play_loading || play_creating ? L"true" : L"false", back ? L"true" : L"false", forward ? L"true" : L"false");
    CoTaskMemFree(source);
    CoTaskMemFree(title);
}

static void play_report(void) {
    if (!main_view) return;
    static wchar_t state[TEXT_MAX + 1200], message[TEXT_MAX + 1300];
    play_state_json(state, sizeof state / sizeof *state);
    swprintf(message, sizeof message / sizeof *message, L"{\"event\":\"playstate\",\"detail\":%ls}", state);
    ICoreWebView2_PostWebMessageAsJson(main_view, message);
}

static void play_navigate(const wchar_t *url) {
    if (!is_web(url)) return;
    wcsncpy(play_pending, url, TEXT_MAX - 1);
    if (play_view) ICoreWebView2_Navigate(play_view, url);
}

static void play_fit(void) {
    RECT r;
    GetClientRect(play_host, &r);
    if (play_controller) ICoreWebView2Controller_put_Bounds(play_controller, r);
    UINT dpi = GetDpiForWindow(play_host);
    int radius = MulDiv(20, (int)dpi, 96);
    SetWindowRgn(play_host, CreateRoundRectRgn(0, 0, r.right + 1, r.bottom + 1, radius, radius), TRUE);
}

static HRESULT STDMETHODCALLTYPE on_play_navigation_starting(ICoreWebView2NavigationStartingEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NavigationStartingEventArgs *args);
static HRESULT STDMETHODCALLTYPE on_play_navigation_completed(ICoreWebView2NavigationCompletedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NavigationCompletedEventArgs *args);
static HRESULT STDMETHODCALLTYPE on_play_changed(ICoreWebView2HistoryChangedEventHandler *self, ICoreWebView2 *sender, IUnknown *args);
static HRESULT STDMETHODCALLTYPE on_title_changed(ICoreWebView2DocumentTitleChangedEventHandler *self, ICoreWebView2 *sender, IUnknown *args);
static HRESULT STDMETHODCALLTYPE on_play_source_changed(ICoreWebView2SourceChangedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2SourceChangedEventArgs *args);
HANDLER(play_navigation_starting, ICoreWebView2NavigationStartingEventHandler, on_play_navigation_starting)
HANDLER(play_navigation_completed, ICoreWebView2NavigationCompletedEventHandler, on_play_navigation_completed)
HANDLER(play_history_changed, ICoreWebView2HistoryChangedEventHandler, on_play_changed)
HANDLER(title_changed, ICoreWebView2DocumentTitleChangedEventHandler, on_title_changed)
HANDLER(play_source_changed, ICoreWebView2SourceChangedEventHandler, on_play_source_changed)

static void apply_settings(ICoreWebView2 *view) {
    ICoreWebView2Settings *settings;
    if (FAILED(ICoreWebView2_get_Settings(view, &settings))) return;
    wchar_t devtools[4];
    ICoreWebView2Settings_put_AreDevToolsEnabled(settings, GetEnvironmentVariableW(L"VSG_DEVTOOLS", devtools, 4) > 0);
    ICoreWebView2Settings_put_IsStatusBarEnabled(settings, FALSE);
    ICoreWebView2Settings_Release(settings);
}

static HRESULT STDMETHODCALLTYPE on_play_created(ICoreWebView2CreateCoreWebView2ControllerCompletedHandler *self, HRESULT result, ICoreWebView2Controller *controller) {
    (void)self;
    play_creating = 0;
    if (FAILED(result) || !controller) { play_report(); return S_OK; }
    play_controller = controller;
    ICoreWebView2Controller_AddRef(controller);
    ICoreWebView2Controller_get_CoreWebView2(controller, &play_view);
    apply_settings(play_view);
    EventRegistrationToken token;
    ICoreWebView2_add_NavigationStarting(play_view, AS(ICoreWebView2NavigationStartingEventHandler, play_navigation_starting), &token);
    ICoreWebView2_add_NavigationCompleted(play_view, AS(ICoreWebView2NavigationCompletedEventHandler, play_navigation_completed), &token);
    ICoreWebView2_add_HistoryChanged(play_view, AS(ICoreWebView2HistoryChangedEventHandler, play_history_changed), &token);
    ICoreWebView2_add_DocumentTitleChanged(play_view, AS(ICoreWebView2DocumentTitleChangedEventHandler, title_changed), &token);
    ICoreWebView2_add_SourceChanged(play_view, AS(ICoreWebView2SourceChangedEventHandler, play_source_changed), &token);
    play_fit();
    if (play_pending[0]) ICoreWebView2_Navigate(play_view, play_pending);
    play_report();
    return S_OK;
}
HANDLER(play_created, ICoreWebView2CreateCoreWebView2ControllerCompletedHandler, on_play_created)

static HRESULT STDMETHODCALLTYPE on_play_navigation_starting(ICoreWebView2NavigationStartingEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NavigationStartingEventArgs *args) {
    (void)self; (void)sender;
    LPWSTR uri = NULL;
    ICoreWebView2NavigationStartingEventArgs_get_Uri(args, &uri);
    if (uri && !is_web(uri) && !starts_with(uri, L"about:") && !starts_with(uri, L"data:") && !starts_with(uri, L"blob:")) {
        ICoreWebView2NavigationStartingEventArgs_put_Cancel(args, TRUE);
        ShellExecuteW(NULL, L"open", uri, NULL, NULL, SW_SHOWNORMAL);
    } else {
        play_loading = 1;
        play_report();
    }
    CoTaskMemFree(uri);
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE on_play_navigation_completed(ICoreWebView2NavigationCompletedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NavigationCompletedEventArgs *args) {
    (void)self; (void)sender; (void)args;
    play_loading = 0;
    play_report();
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE on_play_changed(ICoreWebView2HistoryChangedEventHandler *self, ICoreWebView2 *sender, IUnknown *args) {
    (void)self; (void)sender; (void)args;
    play_report();
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE on_play_source_changed(ICoreWebView2SourceChangedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2SourceChangedEventArgs *args) {
    (void)self; (void)sender; (void)args;
    play_report();
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE on_title_changed(ICoreWebView2DocumentTitleChangedEventHandler *self, ICoreWebView2 *sender, IUnknown *args) {
    (void)self; (void)args;
    if (sender != main_view) { play_report(); return S_OK; }
    LPWSTR title = NULL;
    ICoreWebView2_get_DocumentTitle(sender, &title);
    SetWindowTextW(window, title && *title ? title : L"VS Gammon");
    CoTaskMemFree(title);
    return S_OK;
}

static void play_hide(void) {
    if (GetFocus() && IsChild(play_host, GetFocus()) && main_controller)
        ICoreWebView2Controller_MoveFocus(main_controller, COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
    ShowWindow(play_host, SW_HIDE);
}

/* Page → app: args {action: show|frame|hide|go|back|forward|reload|stop, url?, rect? (CSS px), scale?}. */
static void play_handle(const wchar_t *args) {
    static wchar_t action[32], url[TEXT_MAX];
    json_string(args, L"action", action, 32);
    json_string(args, L"url", url, TEXT_MAX);
    if (!wcscmp(action, L"show") || !wcscmp(action, L"frame")) {
        const wchar_t *rect = json_value(args, L"rect");
        if (rect) {
            double scale = json_number(args, L"scale", 1);
            int x = (int)(json_number(rect, L"x", 0) * scale + 0.5), y = (int)(json_number(rect, L"y", 0) * scale + 0.5);
            int w = (int)(json_number(rect, L"width", 0) * scale + 0.5), h = (int)(json_number(rect, L"height", 0) * scale + 0.5);
            SetWindowPos(play_host, HWND_TOP, x, y, w, h, SWP_NOACTIVATE);
            play_fit();
        }
        if (!wcscmp(action, L"show")) {
            ShowWindow(play_host, SW_SHOWNA);
            if (!play_controller && !play_creating) {
                if (!play_pending[0] && is_web(url)) wcsncpy(play_pending, url, TEXT_MAX - 1);
                play_creating = 1;
                ICoreWebView2Environment_CreateCoreWebView2Controller(environment, play_host, AS(ICoreWebView2CreateCoreWebView2ControllerCompletedHandler, play_created));
            }
        }
    } else if (!wcscmp(action, L"hide")) play_hide();
    else if (!wcscmp(action, L"go")) play_navigate(url);
    else if (play_view && !wcscmp(action, L"back")) ICoreWebView2_GoBack(play_view);
    else if (play_view && !wcscmp(action, L"forward")) ICoreWebView2_GoForward(play_view);
    else if (play_view && !wcscmp(action, L"reload")) ICoreWebView2_Reload(play_view);
    else if (play_view && !wcscmp(action, L"stop")) ICoreWebView2_Stop(play_view);
}

/* ---------- screenshots of the game view for live stats (one at a time; the page asks again when it is done) ---------- */

static IStream *snapshot_stream;
static int snapshot_id;

static void snapshot_reply(const wchar_t *base64) {
    size_t size = (base64 ? wcslen(base64) : 0) + 64;
    wchar_t *reply = malloc(size * sizeof(wchar_t));
    if (!reply) return;
    if (base64) swprintf(reply, size, L"{\"id\":%d,\"result\":{\"image\":\"%ls\"}}", snapshot_id, base64);
    else swprintf(reply, size, L"{\"id\":%d,\"result\":null}", snapshot_id);
    ICoreWebView2_PostWebMessageAsJson(main_view, reply);
    free(reply);
}

static HRESULT STDMETHODCALLTYPE on_snapshot(ICoreWebView2CapturePreviewCompletedHandler *self, HRESULT result) {
    (void)self;
    IStream *stream = snapshot_stream;
    snapshot_stream = NULL;
    wchar_t *base64 = NULL;
    HGLOBAL memory = NULL;
    STATSTG stat;
    if (SUCCEEDED(result) && SUCCEEDED(GetHGlobalFromStream(stream, &memory)) && SUCCEEDED(IStream_Stat(stream, &stat, STATFLAG_NONAME))) {
        DWORD bytes = (DWORD)stat.cbSize.QuadPart, chars = 0;
        const BYTE *data = GlobalLock(memory);
        if (data && CryptBinaryToStringW(data, bytes, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, NULL, &chars)) {
            base64 = malloc(chars * sizeof(wchar_t));
            if (base64 && !CryptBinaryToStringW(data, bytes, CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF, base64, &chars)) {
                free(base64);
                base64 = NULL;
            }
        }
        if (data) GlobalUnlock(memory);
    }
    snapshot_reply(base64);
    free(base64);
    if (stream) IStream_Release(stream);
    return S_OK;
}
HANDLER(snapshot_done, ICoreWebView2CapturePreviewCompletedHandler, on_snapshot)

/* Returns 1 when the reply comes later, from on_snapshot. */
static int play_snapshot(int id) {
    if (!play_view || !IsWindowVisible(play_host) || snapshot_stream) return 0;
    if (FAILED(CreateStreamOnHGlobal(NULL, TRUE, &snapshot_stream))) {
        snapshot_stream = NULL;
        return 0;
    }
    snapshot_id = id;
    if (FAILED(ICoreWebView2_CapturePreview(play_view, COREWEBVIEW2_CAPTURE_PREVIEW_IMAGE_FORMAT_PNG, snapshot_stream,
                                            AS(ICoreWebView2CapturePreviewCompletedHandler, snapshot_done)))) {
        IStream_Release(snapshot_stream);
        snapshot_stream = NULL;
        return 0;
    }
    return 1;
}

/* ---------- the app view ---------- */

static HRESULT STDMETHODCALLTYPE on_message(ICoreWebView2WebMessageReceivedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2WebMessageReceivedEventArgs *args) {
    (void)self; (void)sender;
    LPWSTR source = NULL, json = NULL;
    ICoreWebView2WebMessageReceivedEventArgs_get_Source(args, &source);
    ICoreWebView2WebMessageReceivedEventArgs_get_WebMessageAsJson(args, &json);
    if (starts_with(source, URL) && json) {
        wchar_t name[32];
        int id = (int)json_number(json, L"id", 0);
        json_string(json, L"name", name, 32);
        static wchar_t state[TEXT_MAX + 1200], reply[TEXT_MAX + 1300];
        const wchar_t *call_args = json_value(json, L"args");
        wchar_t action[32] = L"";
        if (call_args) json_string(call_args, L"action", action, 32);
        if (!wcscmp(name, L"play") && !wcscmp(action, L"snapshot")) {
            if (play_snapshot(id)) {
                CoTaskMemFree(source);
                CoTaskMemFree(json);
                return S_OK;
            }
            swprintf(reply, sizeof reply / sizeof *reply, L"{\"id\":%d,\"result\":null}", id);
        } else if (!wcscmp(name, L"play")) {
            play_handle(call_args ? call_args : L"");
            play_state_json(state, sizeof state / sizeof *state);
            swprintf(reply, sizeof reply / sizeof *reply, L"{\"id\":%d,\"result\":%ls}", id, state);
        } else {
            swprintf(reply, sizeof reply / sizeof *reply, L"{\"id\":%d,\"error\":\"unknown call\"}", id);
        }
        ICoreWebView2_PostWebMessageAsJson(main_view, reply);
    }
    CoTaskMemFree(source);
    CoTaskMemFree(json);
    return S_OK;
}
HANDLER(message_received, ICoreWebView2WebMessageReceivedEventHandler, on_message)

static HRESULT STDMETHODCALLTYPE on_main_navigation_starting(ICoreWebView2NavigationStartingEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NavigationStartingEventArgs *args) {
    (void)self; (void)sender;
    LPWSTR uri = NULL;
    ICoreWebView2NavigationStartingEventArgs_get_Uri(args, &uri);
    if (uri && !starts_with(uri, URL) && !starts_with(uri, L"file:") && !starts_with(uri, L"about:") && !starts_with(uri, L"blob:") && !starts_with(uri, L"data:")) {
        ICoreWebView2NavigationStartingEventArgs_put_Cancel(args, TRUE);
        ShellExecuteW(NULL, L"open", uri, NULL, NULL, SW_SHOWNORMAL);
    }
    CoTaskMemFree(uri);
    return S_OK;
}
HANDLER(main_navigation_starting, ICoreWebView2NavigationStartingEventHandler, on_main_navigation_starting)

static HRESULT STDMETHODCALLTYPE on_main_source_changed(ICoreWebView2SourceChangedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2SourceChangedEventArgs *args) {
    (void)self; (void)args;
    LPWSTR source = NULL;
    ICoreWebView2_get_Source(sender, &source);
    if (!starts_with(source, URL L"play")) play_hide();
    CoTaskMemFree(source);
    return S_OK;
}
HANDLER(main_source_changed, ICoreWebView2SourceChangedEventHandler, on_main_source_changed)

static HRESULT STDMETHODCALLTYPE on_main_new_window(ICoreWebView2NewWindowRequestedEventHandler *self, ICoreWebView2 *sender, ICoreWebView2NewWindowRequestedEventArgs *args) {
    (void)self; (void)sender;
    LPWSTR uri = NULL;
    ICoreWebView2NewWindowRequestedEventArgs_get_Uri(args, &uri);
    if (uri && is_web(uri)) ShellExecuteW(NULL, L"open", uri, NULL, NULL, SW_SHOWNORMAL);
    ICoreWebView2NewWindowRequestedEventArgs_put_Handled(args, TRUE);
    CoTaskMemFree(uri);
    return S_OK;
}
HANDLER(main_new_window, ICoreWebView2NewWindowRequestedEventHandler, on_main_new_window)

static HRESULT STDMETHODCALLTYPE on_main_created(ICoreWebView2CreateCoreWebView2ControllerCompletedHandler *self, HRESULT result, ICoreWebView2Controller *controller) {
    (void)self;
    if (FAILED(result) || !controller) {
        open_in_browser = 1;
        DestroyWindow(window);
        return S_OK;
    }
    main_controller = controller;
    ICoreWebView2Controller_AddRef(controller);
    ICoreWebView2Controller_get_CoreWebView2(controller, &main_view);
    apply_settings(main_view);
    EventRegistrationToken token;
    ICoreWebView2_add_WebMessageReceived(main_view, AS(ICoreWebView2WebMessageReceivedEventHandler, message_received), &token);
    ICoreWebView2_add_NavigationStarting(main_view, AS(ICoreWebView2NavigationStartingEventHandler, main_navigation_starting), &token);
    ICoreWebView2_add_SourceChanged(main_view, AS(ICoreWebView2SourceChangedEventHandler, main_source_changed), &token);
    ICoreWebView2_add_NewWindowRequested(main_view, AS(ICoreWebView2NewWindowRequestedEventHandler, main_new_window), &token);
    ICoreWebView2_add_DocumentTitleChanged(main_view, AS(ICoreWebView2DocumentTitleChangedEventHandler, title_changed), &token);
    RECT r;
    GetClientRect(window, &r);
    ICoreWebView2Controller_put_Bounds(controller, r);
    SetWindowPos(play_host, HWND_TOP, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    ICoreWebView2Controller_MoveFocus(controller, COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
    static wchar_t start[6 * MAX_PATH];
    if (server_up) wcscpy(start, URL);
    else starting_page_url(start, 6 * MAX_PATH);
    ICoreWebView2_Navigate(main_view, start);
    return S_OK;
}
HANDLER(main_created, ICoreWebView2CreateCoreWebView2ControllerCompletedHandler, on_main_created)

static HRESULT STDMETHODCALLTYPE on_environment(ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler *self, HRESULT result, ICoreWebView2Environment *created) {
    (void)self;
    if (FAILED(result) || !created) {
        open_in_browser = 1;
        DestroyWindow(window);
        return S_OK;
    }
    environment = created;
    ICoreWebView2Environment_AddRef(created);
    ICoreWebView2Environment_CreateCoreWebView2Controller(created, window, AS(ICoreWebView2CreateCoreWebView2ControllerCompletedHandler, main_created));
    return S_OK;
}
HANDLER(environment_created, ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler, on_environment)

typedef HRESULT(STDAPICALLTYPE *create_environment_fn)(PCWSTR, PCWSTR, ICoreWebView2EnvironmentOptions *,
                                                       ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler *);

static int start_webview(void) {
    wchar_t loader_path[MAX_PATH], profile[MAX_PATH];
    swprintf(loader_path, MAX_PATH, L"%ls\\WebView2Loader.dll", app_dir);
    HMODULE loader = LoadLibraryW(loader_path);
    if (!loader) return 0;
    create_environment_fn create = (create_environment_fn)(void *)GetProcAddress(loader, "CreateCoreWebView2EnvironmentWithOptions");
    swprintf(profile, MAX_PATH, L"%ls\\webview", data_dir);
    return create && SUCCEEDED(create(NULL, profile, NULL, AS(ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler, environment_created)));
}

/* ---------- windows ---------- */

static void placement_path(wchar_t *path) { swprintf(path, MAX_PATH, L"%ls\\window.dat", data_dir); }

static void save_placement(void) {
    WINDOWPLACEMENT placement = {sizeof placement};
    wchar_t path[MAX_PATH];
    placement_path(path);
    if (!GetWindowPlacement(window, &placement)) return;
    FILE *f = _wfopen(path, L"wb");
    if (f) { fwrite(&placement, sizeof placement, 1, f); fclose(f); }
}

static void restore_placement(int show) {
    WINDOWPLACEMENT placement = {0};
    wchar_t path[MAX_PATH];
    placement_path(path);
    FILE *f = _wfopen(path, L"rb");
    int ok = f && fread(&placement, sizeof placement, 1, f) == 1 && placement.length == sizeof placement;
    if (f) fclose(f);
    if (ok) {
        if (placement.showCmd == SW_SHOWMINIMIZED) placement.showCmd = SW_SHOWNORMAL;
        SetWindowPlacement(window, &placement);
    } else {
        ShowWindow(window, show);
    }
}

static void follow_system_theme(void) {
    DWORD light = 1, size = sizeof light;
    RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize", L"AppsUseLightTheme",
                 RRF_RT_REG_DWORD, NULL, &light, &size);
    BOOL dark = light == 0;
    DwmSetWindowAttribute(window, 20 /* DWMWA_USE_IMMERSIVE_DARK_MODE */, &dark, sizeof dark);
}

static LRESULT CALLBACK play_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_SIZE) { play_fit(); return 0; }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    switch (message) {
        case WM_SIZE:
            if (main_controller) {
                RECT r;
                GetClientRect(hwnd, &r);
                ICoreWebView2Controller_put_Bounds(main_controller, r);
            }
            return 0;
        case WM_MOVE:
            if (main_controller) ICoreWebView2Controller_NotifyParentWindowPositionChanged(main_controller);
            if (play_controller) ICoreWebView2Controller_NotifyParentWindowPositionChanged(play_controller);
            return 0;
        case WM_SETFOCUS:
            if (main_controller) ICoreWebView2Controller_MoveFocus(main_controller, COREWEBVIEW2_MOVE_FOCUS_REASON_PROGRAMMATIC);
            return 0;
        case WM_GETMINMAXINFO: {
            UINT dpi = GetDpiForWindow(hwnd);
            ((MINMAXINFO *)lparam)->ptMinTrackSize.x = MulDiv(480, (int)dpi, 96);
            ((MINMAXINFO *)lparam)->ptMinTrackSize.y = MulDiv(480, (int)dpi, 96);
            return 0;
        }
        case WM_DPICHANGED: {
            RECT *r = (RECT *)lparam;
            SetWindowPos(hwnd, NULL, r->left, r->top, r->right - r->left, r->bottom - r->top, SWP_NOZORDER | SWP_NOACTIVATE);
            return 0;
        }
        case WM_SETTINGCHANGE:
            follow_system_theme();
            break;
        case WM_TIMER:
            if (WaitForSingleObject(server_process, 0) == WAIT_OBJECT_0)
                fail(server_up ? L"The VS Gammon server stopped unexpectedly. Open VS Gammon again."
                               : L"The VS Gammon server stopped while starting.");
            if (!server_up && !(server_up = server_ready()) && GetTickCount() - started_at > START_TIMEOUT_MS) {
                TerminateProcess(server_process, 1);
                fail(L"The VS Gammon server did not start within two and a half minutes.");
            }
            return 0;
        case WM_CLOSE:
            save_placement();
            DestroyWindow(hwnd);
            return 0;
        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

static int open_window(HINSTANCE instance, int show) {
    WNDCLASSEXW main_class = {sizeof main_class};
    main_class.lpfnWndProc = window_proc;
    main_class.hInstance = instance;
    main_class.hIcon = LoadIconW(instance, MAKEINTRESOURCEW(1));
    main_class.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_ARROW);
    main_class.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    main_class.lpszClassName = WINDOW_CLASS;
    WNDCLASSEXW play_class = {sizeof play_class};
    play_class.lpfnWndProc = play_proc;
    play_class.hInstance = instance;
    play_class.hCursor = main_class.hCursor;
    play_class.lpszClassName = PLAY_CLASS;
    if (!RegisterClassExW(&main_class) || !RegisterClassExW(&play_class)) return 0;
    UINT dpi = GetDpiForSystem();
    window = CreateWindowExW(0, WINDOW_CLASS, L"VS Gammon", WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT, CW_USEDEFAULT,
                             MulDiv(1320, (int)dpi, 96), MulDiv(880, (int)dpi, 96), NULL, NULL, instance, NULL);
    if (!window) return 0;
    play_host = CreateWindowExW(0, PLAY_CLASS, NULL, WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN, 0, 0, 0, 0, window, NULL, instance, NULL);
    follow_system_theme();
    restore_placement(show);
    UpdateWindow(window);
    return 1;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE prev, PWSTR args, int show) {
    (void)prev; (void)args;
    wchar_t local[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH)) wcscpy(local, L".");
    swprintf(data_dir, MAX_PATH, L"%ls\\VS Gammon", local);
    CreateDirectoryW(data_dir, NULL);
    SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);

    HANDLE mutex = CreateMutexW(NULL, TRUE, L"Local\\VSGammonApp");
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        HWND existing = FindWindowW(WINDOW_CLASS, NULL);
        if (existing) {
            if (IsIconic(existing)) ShowWindow(existing, SW_RESTORE);
            SetForegroundWindow(existing);
        } else {
            ShellExecuteW(NULL, L"open", URL, NULL, NULL, SW_SHOWNORMAL);
        }
        return 0;
    }

    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);
    GetModuleFileNameW(NULL, app_dir, MAX_PATH);
    *wcsrchr(app_dir, L'\\') = 0;
    if (server_ready()) fail(L"Another program is already using port 5565, so VS Gammon cannot start.");

    wchar_t log_path[MAX_PATH], python[MAX_PATH], command[2 * MAX_PATH], path_var[32767], new_path[32767];
    swprintf(log_path, MAX_PATH, L"%ls\\server.log", data_dir);
    swprintf(python, MAX_PATH, L"%ls\\python\\python.exe", app_dir);
    swprintf(command, 2 * MAX_PATH, L"\"%ls\" -m app.desktop", python);
    if (!GetEnvironmentVariableW(L"PATH", path_var, 32767)) path_var[0] = 0;
    swprintf(new_path, 32767, L"%ls\\python;%ls", app_dir, path_var);
    SetEnvironmentVariableW(L"PATH", new_path);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", L"1");

    SECURITY_ATTRIBUTES inherit = {sizeof inherit, NULL, TRUE};
    HANDLE log = CreateFileW(log_path, GENERIC_WRITE, FILE_SHARE_READ, &inherit, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    HANDLE stdin_read, stdin_write;
    CreatePipe(&stdin_read, &stdin_write, &inherit, 0);
    SetHandleInformation(stdin_write, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si = {sizeof si};
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = stdin_read;
    si.hStdOutput = log;
    si.hStdError = log;
    PROCESS_INFORMATION server;
    if (!CreateProcessW(python, command, NULL, NULL, TRUE, CREATE_NO_WINDOW, NULL, app_dir, &si, &server))
        fail(L"The VS Gammon server could not be started.");
    CloseHandle(stdin_read);
    CloseHandle(server.hThread);
    server_process = server.hProcess;
    started_at = GetTickCount();

    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (open_window(instance, show) && start_webview()) {
        SetTimer(window, 1, 500, NULL);
        MSG msg;
        while (GetMessageW(&msg, NULL, 0, 0) > 0) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    } else {
        open_in_browser = 1;
        if (window) DestroyWindow(window);
    }
    if (open_in_browser) {
        while (!server_ready()) {
            if (WaitForSingleObject(server_process, 250) == WAIT_OBJECT_0) fail(L"The VS Gammon server stopped while starting.");
            if (GetTickCount() - started_at > START_TIMEOUT_MS) {
                TerminateProcess(server_process, 1);
                fail(L"The VS Gammon server did not start within two and a half minutes.");
            }
        }
        show_in_browser();
    }

    CloseHandle(stdin_write);
    if (WaitForSingleObject(server_process, 8000) != WAIT_OBJECT_0) TerminateProcess(server_process, 0);
    CloseHandle(server_process);
    if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
    ReleaseMutex(mutex);
    return 0;
}
