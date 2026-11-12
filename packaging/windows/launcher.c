/* VS Gammon for Windows: starts the bundled server (python\python.exe -m app.desktop) and shows it in an
 * Edge app window with its own profile. Closing that window closes the server's stdin, which stops it. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <shellapi.h>
#include <stdio.h>
#include <wchar.h>

#define PORT 5565
#define URL L"http://127.0.0.1:5565/"
#define START_TIMEOUT_MS 60000

static wchar_t app_dir[MAX_PATH];
static wchar_t data_dir[MAX_PATH];

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

static HANDLE open_window(void) {
    wchar_t edge[MAX_PATH], command[4 * MAX_PATH];
    if (!find_edge(edge, MAX_PATH)) return NULL;
    swprintf(command, 4 * MAX_PATH,
             L"\"%ls\" --app=%ls --user-data-dir=\"%ls\\edge\" --no-first-run --no-default-browser-check "
             L"--disable-features=msEdgeStartupBoost --window-size=1320,880",
             edge, URL, data_dir);
    STARTUPINFOW si = {sizeof si};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) return NULL;
    CloseHandle(pi.hThread);
    return pi.hProcess;
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

    HANDLE mutex = CreateMutexW(NULL, TRUE, L"Local\\VSGammonApp");
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        HANDLE window = open_window();
        if (window) CloseHandle(window);
        else ShellExecuteW(NULL, L"open", URL, NULL, NULL, SW_SHOWNORMAL);
        return 0;
    }
    if (server_ready()) fail(L"Another program is already using port 5565, so VS Gammon cannot start.");

    GetModuleFileNameW(NULL, app_dir, MAX_PATH);
    *wcsrchr(app_dir, L'\\') = 0;

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

    DWORD waited = 0;
    while (!server_ready()) {
        if (WaitForSingleObject(server.hProcess, 250) == WAIT_OBJECT_0) fail(L"The VS Gammon server stopped while starting.");
        waited += 250;
        if (waited > START_TIMEOUT_MS) fail(L"The VS Gammon server did not start within a minute.");
    }

    HANDLE window = open_window();
    if (window) {
        WaitForSingleObject(window, INFINITE);
        CloseHandle(window);
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
