#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>


static void show_error(const wchar_t *message) {
    MessageBoxW(NULL, message, L"OddRoom OrderOps", MB_OK | MB_ICONERROR | MB_SETFOREGROUND);
}


int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show_command) {
    (void)instance;
    (void)previous;
    (void)command_line;
    (void)show_command;

    wchar_t executable[32768];
    DWORD length = GetModuleFileNameW(NULL, executable, (DWORD)(sizeof(executable) / sizeof(executable[0])));
    if (length == 0 || length >= (DWORD)(sizeof(executable) / sizeof(executable[0]))) {
        show_error(L"PF07 could not resolve its extracted package path.");
        return 10;
    }
    wchar_t *separator = wcsrchr(executable, L'\\');
    if (separator == NULL) {
        show_error(L"PF07 could not resolve its package directory.");
        return 11;
    }
    *separator = L'\0';

    wchar_t script[32768];
    if (swprintf(script, sizeof(script) / sizeof(script[0]), L"%ls\\Start-PF07.ps1", executable) < 0) {
        show_error(L"PF07 could not construct the launcher path.");
        return 12;
    }
    DWORD attributes = GetFileAttributesW(script);
    if (attributes == INVALID_FILE_ATTRIBUTES || (attributes & FILE_ATTRIBUTE_DIRECTORY) != 0) {
        show_error(L"Start-PF07.ps1 is missing. Extract the complete buyer ZIP and try again.");
        return 13;
    }

    wchar_t command[32768];
    if (swprintf(
            command,
            sizeof(command) / sizeof(command[0]),
            L"powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File \"%ls\" -Action Hub",
            script) < 0) {
        show_error(L"PF07 could not construct the Windows adapter command.");
        return 14;
    }

    STARTUPINFOW startup;
    PROCESS_INFORMATION process;
    ZeroMemory(&startup, sizeof(startup));
    ZeroMemory(&process, sizeof(process));
    startup.cb = sizeof(startup);
    BOOL created = CreateProcessW(
        NULL,
        command,
        NULL,
        NULL,
        FALSE,
        CREATE_UNICODE_ENVIRONMENT | CREATE_NO_WINDOW,
        NULL,
        executable,
        &startup,
        &process);
    if (!created) {
        show_error(L"PF07 could not start Windows PowerShell. Use START-PF07.cmd for the actionable fallback.");
        return 15;
    }

    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD exit_code = 1;
    GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    if (exit_code != 0) {
        show_error(L"PF07 stopped before opening the hub. Run START-PF07.cmd to see the detailed recovery message.");
    }
    return (int)exit_code;
}
