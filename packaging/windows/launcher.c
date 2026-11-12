/* VS Gammon for Windows: starts the bundled server (python\python.exe -m app.desktop) and shows it in an
 * Edge app window with its own profile. The window opens on starting.html, which switches to the app once the
 * server answers. The server runs while any Edge process uses that profile: Edge may hand the window to another
 * process (one already running, or a relaunch after an update), so the process we start says nothing.
 * When the last one is gone, the server's stdin is closed, which stops it. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <shellapi.h>
#include <tlhelp32.h>
#include <winternl.h>
#include <stdio.h>
#include <wchar.h>

#define PORT 5565
#define URL L"http://127.0.0.1:5565/"
#define START_TIMEOUT_MS 150000
#define EDGE_APPEAR_MS 30000
#define EDGE_GONE_CHECKS 3

static wchar_t app_dir[MAX_PATH];
static wchar_t data_dir[MAX_PATH];
static wchar_t profile_dir[MAX_PATH];

static void fail(const wchar_t *message) {
    wchar_t text[1024];
    swprintf(text, 1024, L"%ls\n\nDetails are in %ls\\server.log", message, data_dir);
    MessageBoxW(NULL, text, L"VS Gammon", MB_ICONERROR | MB_OK);
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

static int find_edge(wchar_t *path, DWORD size) {
    const wchar_t *key = L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\msedge.exe";
    HKEY roots[] = {HKEY_LOCAL_MACHINE, HKEY_CURRENT_USER};
    for (int i = 0; i < 2; i++) {
        DWORD bytes = size * sizeof(wchar_t);
        if (RegGetValueW(roots[i], key, NULL, RRF_RT_REG_SZ, NULL, path, &bytes) == ERROR_SUCCESS &&
            GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES)
            return 1;
    }
    const wchar_t *vars[] = {L"ProgramFiles(x86)", L"ProgramFiles"};
    for (int i = 0; i < 2; i++) {
        wchar_t base[MAX_PATH];
        if (GetEnvironmentVariableW(vars[i], base, MAX_PATH)) {
            swprintf(path, size, L"%ls\\Microsoft\\Edge\\Application\\msedge.exe", base);
            if (GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES) return 1;
        }
    }
    return 0;
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

static int open_window(void) {
    wchar_t edge[MAX_PATH], url[6 * MAX_PATH], command[8 * MAX_PATH];
    if (!find_edge(edge, MAX_PATH)) return 0;
    starting_page_url(url, 6 * MAX_PATH);
    swprintf(command, 8 * MAX_PATH,
             L"\"%ls\" --app=\"%ls\" --user-data-dir=\"%ls\" --no-first-run --no-default-browser-check "
             L"--disable-features=msEdgeStartupBoost --window-size=1320,880",
             edge, url, profile_dir);
    STARTUPINFOW si = {sizeof si};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) return 0;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 1;
}

typedef NTSTATUS(NTAPI *query_process_fn)(HANDLE, PROCESSINFOCLASS, PVOID, ULONG, PULONG);
#define PROCESS_COMMAND_LINE_INFORMATION ((PROCESSINFOCLASS)60)

static int uses_app_profile(DWORD pid, const wchar_t *marker) {
    static query_process_fn query;
    static BYTE buffer[70000];
    static wchar_t line[32768];
    if (!query) query = (query_process_fn)GetProcAddress(GetModuleHandleW(L"ntdll.dll"), "NtQueryInformationProcess");
    if (!query) return 0;
    HANDLE process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!process) return 0;
    int found = 0;
    ULONG size = 0;
    if (query(process, PROCESS_COMMAND_LINE_INFORMATION, buffer, sizeof buffer, &size) >= 0) {
        UNICODE_STRING *cmd = (UNICODE_STRING *)buffer;
        size_t chars = cmd->Length / sizeof(wchar_t);
        if (chars >= 32768) chars = 32767;
        wmemcpy(line, cmd->Buffer, chars);
        line[chars] = 0;
        found = wcsstr(_wcslwr(line), marker) != NULL;
    }
    CloseHandle(process);
    return found;
}

static int app_window_open(void) {
    wchar_t marker[MAX_PATH];
    wcscpy(marker, profile_dir);
    _wcslwr(marker);
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return 0;
    PROCESSENTRY32W entry = {sizeof entry};
    int open = 0;
    for (BOOL more = Process32FirstW(snapshot, &entry); more && !open; more = Process32NextW(snapshot, &entry))
        open = _wcsicmp(entry.szExeFile, L"msedge.exe") == 0 && uses_app_profile(entry.th32ProcessID, marker);
    CloseHandle(snapshot);
    return open;
}

static void show_without_edge(void) {
    ShellExecuteW(NULL, L"open", URL, NULL, NULL, SW_SHOWNORMAL);
    MessageBoxW(NULL, L"VS Gammon is open in your browser.\n\nClick OK to quit VS Gammon.", L"VS Gammon",
                MB_ICONINFORMATION | MB_OK);
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE prev, PWSTR args, int show) {
    (void)instance; (void)prev; (void)args; (void)show;
    wchar_t local[MAX_PATH];
    if (!GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH)) wcscpy(local, L".");
    swprintf(data_dir, MAX_PATH, L"%ls\\VS Gammon", local);
    CreateDirectoryW(data_dir, NULL);

    WSADATA wsa;
    WSAStartup(MAKEWORD(2, 2), &wsa);

    GetModuleFileNameW(NULL, app_dir, MAX_PATH);
    *wcsrchr(app_dir, L'\\') = 0;
    swprintf(profile_dir, MAX_PATH, L"%ls\\edge", data_dir);

    HANDLE mutex = CreateMutexW(NULL, TRUE, L"Local\\VSGammonApp");
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        if (!open_window()) ShellExecuteW(NULL, L"open", URL, NULL, NULL, SW_SHOWNORMAL);
        return 0;
    }
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

    int window = open_window();
    DWORD waited = 0;
    while (!server_ready()) {
        if (WaitForSingleObject(server.hProcess, 250) == WAIT_OBJECT_0) fail(L"The VS Gammon server stopped while starting.");
        waited += 250;
        if (waited > START_TIMEOUT_MS) {
            TerminateProcess(server.hProcess, 1);
            fail(L"The VS Gammon server did not start within two and a half minutes.");
        }
    }

    if (window) {
        int seen = 0, gone = 0;
        for (DWORD elapsed = 0;; elapsed += 1000) {
            if (app_window_open()) seen = 1, gone = 0;
            else if (seen ? ++gone >= EDGE_GONE_CHECKS : elapsed >= EDGE_APPEAR_MS) break;
            if (WaitForSingleObject(server.hProcess, 1000) == WAIT_OBJECT_0)
                fail(L"The VS Gammon server stopped unexpectedly. Close the window and open VS Gammon again.");
        }
        if (!seen) show_without_edge();
    } else {
        show_without_edge();
    }

    CloseHandle(stdin_write);
    if (WaitForSingleObject(server.hProcess, 8000) != WAIT_OBJECT_0) TerminateProcess(server.hProcess, 0);
    CloseHandle(server.hProcess);
    if (log != INVALID_HANDLE_VALUE) CloseHandle(log);
    ReleaseMutex(mutex);
    return 0;
}
