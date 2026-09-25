$typeDef = @'
using System;
using System.Runtime.InteropServices;

public class DesktopProcessLauncher {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute;
        public uint dwFlags;
        public short wShowWindow, cbReserved2;
        public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess, hThread;
        public int dwProcessId, dwThreadId;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool CreateProcess(
        string lpApplicationName,
        string lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation
    );

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr hObject);

    public static int Launch(string app, string args, string workingDir) {
        STARTUPINFO si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(si);
        si.lpDesktop = @"WinSta0\default";
        si.dwFlags = 0x00000001; // STARTF_USESHOWWINDOW
        si.wShowWindow = 1;      // SW_SHOWNORMAL

        PROCESS_INFORMATION pi = new PROCESS_INFORMATION();
        string cmd = string.Format("\"{0}\" {1}", app, args);
        bool success = CreateProcess(null, cmd, IntPtr.Zero, IntPtr.Zero, false, 0x00000010, IntPtr.Zero, workingDir, ref si, out pi); // CREATE_NEW_CONSOLE
        if (!success) {
            return -Marshal.GetLastWin32Error();
        }
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 0;
    }
}
'@

if (-not ([System.Management.Automation.PSTypeName]'DesktopProcessLauncher').Type) {
    Add-Type -TypeDefinition $typeDef -Language CSharp
}

$dir = $PSScriptRoot
if (-not $dir) { $dir = (Get-Location).Path }
$batPath = Join-Path $dir "run_network_audit.bat"
$ret = [DesktopProcessLauncher]::Launch("cmd.exe", "/k `"$batPath`"", $dir)
Write-Output "Launched process return code: $ret"

