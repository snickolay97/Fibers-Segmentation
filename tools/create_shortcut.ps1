param([string]$Destination = '')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) { $Destination = Join-Path $taskRoot 'SoLoData.lnk' }
$taskDestination = [System.IO.Path]::GetFullPath($Destination)
$taskIcon = Join-Path $taskRoot 'src\desktop\assets\solodata.ico'
if (-not (Test-Path -LiteralPath $taskIcon)) { throw 'SoLoData icon is missing.' }
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut($taskDestination)
# Resolve launcher and icon from the script location. Quote the launcher path
# separately because Windows passes this string as PowerShell's arguments.
$taskShortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$taskShortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + (Join-Path $taskRoot 'launch_app.ps1') + '" -Shortcut'
$taskShortcut.WorkingDirectory = $taskRoot
$taskShortcut.IconLocation = $taskIcon + ',0'
$taskShortcut.Description = 'SoLoData microscopy application'
$taskShortcut.WindowStyle = 7
$taskShortcut.Save()

# WScript.Shell does not expose System.AppUserModel.ID. Set the Shell Link
# property separately so pinning uses the same taskbar group as app.py.
if (-not ('SoLoDataShortcutIdentity' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class SoLoDataShortcutIdentity
{
    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey
    {
        public Guid FormatId;
        public uint PropertyId;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PropVariant
    {
        public ushort Type, Reserved1, Reserved2, Reserved3;
        public IntPtr Value, Padding;
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    public static void Apply(string filename, string appId)
    {
        var shellLink = Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046"));
        var link = Activator.CreateInstance(shellLink);
        var value = new PropVariant { Type = 31, Value = Marshal.StringToCoTaskMemUni(appId) }; // VT_LPWSTR
        try
        {
            var file = (IPersistFile)link;
            file.Load(filename, 2); // STGM_READWRITE
            var store = (IPropertyStore)link;
            var key = new PropertyKey { FormatId = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), PropertyId = 5 };
            store.SetValue(ref key, ref value);
            store.Commit();
            file.Save(filename, true);
        }
        finally
        {
            Marshal.FreeCoTaskMem(value.Value);
            Marshal.ReleaseComObject(link);
        }
    }
}
'@
}
[SoLoDataShortcutIdentity]::Apply($taskDestination, 'SoLoData.Desktop')
Write-Output $taskDestination
