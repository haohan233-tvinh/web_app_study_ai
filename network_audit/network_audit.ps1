<#
.SYNOPSIS
    Tool Kiem Tra & Thu Thap Thong Tin Chan Mang (Network Restriction Audit & Diagnostic Tool)
    Phien ban: Deep Probe (Timeout 4s, Retry 2x)
.DESCRIPTION
    Tu dong quet va chan doan toan dien cac tang mang:
    1. Thong tin Network Adapter, IP, Gateway, System Proxy
    2. Layer 3: ICMP Ping Egress (8.8.8.8, 1.1.1.1, Gateway)
    3. Layer 7: DNS Hijacking / Local-only vs Public DNS Lookup
    4. Layer 4: Egress Port Whitelist (80, 443, 22, 53, 41641, 51820, 8080)
    5. Captive Portal / HTTP Redirection Detection
    6. Tu dong ket luan mo hinh tuong lua & xuat file bao cao JSON/TXT
#>

[CmdletBinding()]
param (
    [int]$TimeoutSeconds = 4,
    [int]$Retries = 2,
    [string]$OutputDir = ""
)

if (-not $OutputDir) {
    if ($PSScriptRoot) { $OutputDir = $PSScriptRoot } else { $OutputDir = (Get-Location).Path }
}

$ErrorActionPreference = "SilentlyContinue"

# Thiet lap ham in mau sac
function Write-Header ($text) {
    Write-Host "`n$text" -ForegroundColor Cyan
    Write-Host ("=" * ($text.Length + 4)) -ForegroundColor DarkCyan
}

function Write-Result ($name, $status, $detail, $color) {
    $tag = "[$status]".PadRight(10)
    $colName = $name.PadRight(35)
    Write-Host " $tag " -ForegroundColor $color -NoNewline
    Write-Host "$colName : " -ForegroundColor White -NoNewline
    Write-Host "$detail" -ForegroundColor Gray
}

$results = [ordered]@{
    Timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    LocalInfo = @{}
    Layer3_Egress = @{}
    Layer7_DNS = @{}
    Layer4_Ports = @{}
    CaptivePortal = @{}
    Diagnosis = @()
}

Clear-Host
Write-Host "==========================================================================" -ForegroundColor Yellow
Write-Host "    NETWORK RESTRICTION AUDIT TOOL - FULL-STACK DEEP PROBE               " -ForegroundColor Yellow
Write-Host "    Chan doan cac hinh thuc chan mang, loc cong & tuong lua phong thi    " -ForegroundColor Gray
Write-Host "==========================================================================" -ForegroundColor Yellow
Write-Host " Cau hinh quet: Timeout = ${TimeoutSeconds}s/test | So lan thu lai = ${Retries}x`n" -ForegroundColor DarkGray

# -------------------------------------------------------------------------
# 1. THU THAP THONG TIN CUC BO & PROXY
# -------------------------------------------------------------------------
Write-Header "[1/5] THONG TIN MANG NOI BO & CAU HINH HE THONG"

# Uu tien card mang co RouteMetric thap nhat den 0.0.0.0/0 (mang Internet thuc su)
$bestRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
$activeAdapter = $null
if ($bestRoute) {
    $activeAdapter = Get-NetIPConfiguration -InterfaceAlias $bestRoute.InterfaceAlias -ErrorAction SilentlyContinue
}
if (-not $activeAdapter) {
    $activeAdapter = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | Select-Object -First 1
}

$ipAddr = if ($activeAdapter.IPv4Address) { ($activeAdapter.IPv4Address.IPAddress | Select-Object -First 1) } else { "N/A" }
$gateway = if ($bestRoute.NextHop) { $bestRoute.NextHop } elseif ($activeAdapter.IPv4DefaultGateway) { $activeAdapter.IPv4DefaultGateway.NextHop } else { $null }
$dnsServers = if ($activeAdapter.DNSServer.ServerAddresses) { ($activeAdapter.DNSServer.ServerAddresses) -join ", " } else { "N/A" }
$adapterName = if ($activeAdapter.InterfaceAlias) { $activeAdapter.InterfaceAlias } else { "Unknown" }

$results.LocalInfo["Interface"] = $adapterName
$results.LocalInfo["IPv4"] = $ipAddr
$results.LocalInfo["DefaultGateway"] = $gateway
$results.LocalInfo["DNSServers"] = $dnsServers

Write-Result "Network Adapter" "INFO" "$adapterName" Cyan
Write-Result "IPv4 Cuc bo" "INFO" "$ipAddr" Cyan
Write-Result "Default Gateway" "INFO" "$gateway" Cyan
Write-Result "Local DNS Servers" "INFO" "$dnsServers" Cyan

# Kiem tra System Proxy
$proxyReg = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
$proxyEnabled = $proxyReg.ProxyEnable -eq 1
$proxyServer = $proxyReg.ProxyServer
$results.LocalInfo["ProxyEnabled"] = $proxyEnabled
$results.LocalInfo["ProxyServer"] = $proxyServer

if ($proxyEnabled) {
    Write-Result "System HTTP Proxy" "ACTIVE" "Phat hien Proxy dang bat: $proxyServer" Yellow
} else {
    Write-Result "System HTTP Proxy" "NONE" "Khong su dung Proxy cuc bo (Direct Connection)" Green
}

# -------------------------------------------------------------------------
# 2. KIEM TRA LAYER 3: ICMP PING & DINH TUYEN RA INTERNET
# -------------------------------------------------------------------------
Write-Header "[2/5] LAYER 3: KIEM TRA DINH TUYEN & ICMP REACHABILITY"

function Test-PingEndpoint ($target, $label) {
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            $p = New-Object System.Net.NetworkInformation.Ping
            $reply = $p.Send($target, [int]($TimeoutSeconds * 1000))
            if ($reply.Status -eq [System.Net.NetworkInformation.IPStatus]::Success) {
                return @{ Success = $true; Latency = "$($reply.RoundtripTime)ms" }
            }
        } catch {}
    }
    return @{ Success = $false; Latency = "Timeout" }
}

# Ping Gateway
if ($gateway) {
    $gwRes = Test-PingEndpoint $gateway "Default Gateway"
    $results.Layer3_Egress["Gateway"] = $gwRes
    if ($gwRes.Success) {
        Write-Result "Ping Default Gateway ($gateway)" "PASS" "Thong suot ($($gwRes.Latency))" Green
    } else {
        Write-Result "Ping Default Gateway ($gateway)" "FAIL" "Mat goi / Khong phan hoi" Red
    }
}

# Ping Public IPs
$pingTargets = @(
    @{ IP = "8.8.8.8"; Name = "Google Public DNS (8.8.8.8)" },
    @{ IP = "1.1.1.1"; Name = "Cloudflare DNS (1.1.1.1)" }
)

foreach ($pt in $pingTargets) {
    $res = Test-PingEndpoint $pt.IP $pt.Name
    $results.Layer3_Egress[$pt.IP] = $res
    if ($res.Success) {
        Write-Result "Ping $($pt.Name)" "OPEN" "ICMP thong ra Internet ($($res.Latency))" Green
    } else {
        Write-Result "Ping $($pt.Name)" "BLOCKED" "Bi DROP hoac Khong co Route ra ngoai" Red
    }
}

# -------------------------------------------------------------------------
# 3. KIEM TRA LAYER 7: PHAN GIAI DNS & DNS SINKHOLE / HIJACKING
# -------------------------------------------------------------------------
Write-Header "[3/5] LAYER 7: KIEM TRA PHAN GIAI TEN MIEN (DNS)"

$dnsTestDomains = @(
    @{ Domain = "google.com"; Type = "Public" },
    @{ Domain = "github.com"; Type = "Public" },
    @{ Domain = "usth.edu.vn"; Type = "Institutional" }
)

foreach ($dt in $dnsTestDomains) {
    $resolvedIP = $null
    for ($i = 1; $i -le $Retries; $i++) {
        $lookup = Resolve-DnsName -Name $dt.Domain -Type A -QuickTimeout -ErrorAction SilentlyContinue
        if ($lookup -and $lookup.IPAddress) {
            $resolvedIP = ($lookup.IPAddress | Select-Object -First 1)
            break
        }
    }
    $status = if ($resolvedIP) { "SUCCESS" } else { "FAIL" }
    $results.Layer7_DNS[$dt.Domain] = @{ Status = $status; ResolvedIP = $resolvedIP }
    if ($resolvedIP) {
        Write-Result "DNS Resolve $($dt.Domain)" "RESOLVED" "IP: $resolvedIP" Green
    } else {
        Write-Result "DNS Resolve $($dt.Domain)" "BLOCKED" "Khong phan giai duoc (NXDOMAIN / Timeout)" Red
    }
}

# Kiem tra co cho phep tu truy van DNS Server ngoai (Bypass Local DNS qua 8.8.8.8:53)
$directDnsResolved = $null
try {
    $directLookup = Resolve-DnsName -Name "cloudflare.com" -Server "8.8.8.8" -Type A -QuickTimeout -ErrorAction SilentlyContinue
    if ($directLookup -and $directLookup.IPAddress) {
        $directDnsResolved = ($directLookup.IPAddress | Select-Object -First 1)
    }
} catch {}

$results.Layer7_DNS["Direct_8.8.8.8_Query"] = ($directDnsResolved -ne $null)
if ($directDnsResolved) {
    Write-Result "Direct External DNS (8.8.8.8:53)" "OPEN" "Cho phep tu chon DNS ngoai (Khong chan Port 53)" Green
} else {
    Write-Result "Direct External DNS (8.8.8.8:53)" "BLOCKED" "Chan hoac Hijack truy van DNS ra ngoai" Yellow
}

# -------------------------------------------------------------------------
# 4. KIEM TRA LAYER 4: EGRESS TCP / UDP PORT WHITELISTING
# -------------------------------------------------------------------------
Write-Header "[4/5] LAYER 4: KIEM TRA MO CONG RA NGOAI (PORT SCAN)"

function Test-TcpPortDirect ($target, $port) {
    $tcpSuccess = $false
    $latencyMs = 0
    for ($i = 1; $i -le $Retries; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $iar = $client.BeginConnect($target, $port, $null, $null)
            $wait = $iar.AsyncWaitHandle.WaitOne([int]($TimeoutSeconds * 1000), $false)
            if ($wait -and $client.Connected) {
                $client.EndConnect($iar)
                $sw.Stop()
                $tcpSuccess = $true
                $latencyMs = $sw.ElapsedMilliseconds
                $client.Close()
                break
            }
        } catch {
            # failed
        } finally {
            $client.Close()
        }
    }
    return @{ Open = $tcpSuccess; Latency = "$($latencyMs)ms" }
}

$portTargets = @(
    @{ Name = "Web HTTP (Port 80)"; Host = "1.1.1.1"; Port = 80; Service = "Web Duyet mang" },
    @{ Name = "Web HTTPS (Port 443)"; Host = "1.1.1.1"; Port = 443; Service = "Web Bao mat SSL" },
    @{ Name = "SSH (Port 22)"; Host = "github.com"; Port = 22; Service = "Terminal / Git SSH" },
    @{ Name = "DNS TCP (Port 53)"; Host = "8.8.8.8"; Port = 53; Service = "DNS over TCP" },
    @{ Name = "Tailscale DERP (Port 443)"; Host = "derp1.tailscale.com"; Port = 443; Service = "Tailscale Relay" },
    @{ Name = "Alternative HTTP (Port 8080)"; Host = "1.1.1.1"; Port = 8080; Service = "Proxy / Dev Server" }
)

foreach ($pt in $portTargets) {
    $res = Test-TcpPortDirect $pt.Host $pt.Port
    $results.Layer4_Ports["$($pt.Host):$($pt.Port)"] = $res
    if ($res.Open) {
        Write-Result "$($pt.Name)" "OPEN" "Ket noi TCP thanh cong ($($res.Latency))" Green
    } else {
        Write-Result "$($pt.Name)" "BLOCKED" "Tuong lua DROP / Bi chan cong $($pt.Port)" Red
    }
}

# -------------------------------------------------------------------------
# 5. PHAT HIEN CAPTIVE PORTAL & HTTP REDIRECTION
# -------------------------------------------------------------------------
Write-Header "[5/5] PHAT HIEN CAPTIVE PORTAL & CHUYEN HUONG MANG"

$captiveDetected = $false
$captiveDetail = "Khong phat hien Captive Portal"

try {
    $req = [System.Net.HttpWebRequest]::Create("http://connectivitycheck.gstatic.com/generate_204")
    $req.Timeout = $TimeoutSeconds * 1000
    $req.AllowAutoRedirect = $false
    $resp = $req.GetResponse()
    $statusCode = [int]$resp.StatusCode

    if ($statusCode -eq 204) {
        $captiveDetail = "Duong truyen Internet tu do (HTTP 204 No Content chuan)"
    } elseif ($statusCode -eq 302 -or $statusCode -eq 301) {
        $captiveDetected = $true
        $redirectUrl = $resp.Headers["Location"]
        $captiveDetail = "Phat hien chuyen huong dang nhap (Redirect: $redirectUrl)"
    } else {
        $captiveDetail = "Ma phan hoi HTTP bat thuong: $statusCode"
    }
    $resp.Close()
} catch [System.Net.WebException] {
    if ($_.Response) {
        $statusCode = [int]$_.Response.StatusCode
        if ($statusCode -eq 302 -or $statusCode -eq 301) {
            $captiveDetected = $true
            $captiveDetail = "Chuyen huong trang Login Wi-Fi truong (Redirect)"
        }
    } else {
        $captiveDetail = "Khong the gui HTTP Request ra ngoai (Timeout / Chan hoan toan)"
    }
} catch {
    $captiveDetail = "Loi ket noi kiem tra: $($_.Exception.Message)"
}

$results.CaptivePortal["Detected"] = $captiveDetected
$results.CaptivePortal["Detail"] = $captiveDetail

if ($captiveDetected) {
    Write-Result "Captive Portal Detection" "WARNING" "$captiveDetail" Yellow
} else {
    Write-Result "Captive Portal Detection" "CLEAR" "$captiveDetail" Green
}

# -------------------------------------------------------------------------
# 6. TONG HOP KET LUAN MO HINH CHAN (DIAGNOSIS)
# -------------------------------------------------------------------------
Write-Header "KET LUAN CHAN DOAN MO HINH TUONG LUA"

$isPingBlocked = (-not $results.Layer3_Egress["8.8.8.8"].Success) -and (-not $results.Layer3_Egress["1.1.1.1"].Success)
$isDnsBlocked = (-not $results.Layer7_DNS["google.com"].ResolvedIP) -and (-not $results.Layer7_DNS["github.com"].ResolvedIP)
$isWebBlocked = (-not $results.Layer4_Ports["1.1.1.1:80"].Open) -and (-not $results.Layer4_Ports["1.1.1.1:443"].Open)
$isSshBlocked = (-not $results.Layer4_Ports["github.com:22"].Open)

$conclusions = @()

if ($isPingBlocked -and $isDnsBlocked -and $isWebBlocked) {
    $conclusions += "MANG CO LAP NOI BO (Air-gapped / Isolated Intranet Subnet): Tuong lua chan 100% luu luong ra Internet cong cong. Moi giai phap VPN, Tailscale, Proxy ra ngoai deu BAT KHA THI."
} elseif ($isWebBlocked) {
    $conclusions += "CHAN INTERNET RA NGOAI (Total Egress Block): Khong the ket noi toi cac dich vu web cong cong."
} else {
    if ($isPingBlocked) {
        $conclusions += "CHAN ICMP PING: Tuong lua cam Ping ra ngoai de an mang, nhung cac cong Web TCP van co the thong."
    }
    if ($isDnsBlocked) {
        $conclusions += "CHAN / HIJACK DNS: Chi cho phep phan giai domain noi bo truong, ten mien ngoai bi chan."
    }
    if ($isSshBlocked) {
        $conclusions += "LOC CONG NGHIEM NGAT (Port Whitelisting): Chan cong SSH (22) va cac giao thuc mang la."
    }
    if ($captiveDetected) {
        $conclusions += "YEU CAU DANG NHAP MANG (Captive Portal): Can dang nhap tai khoan sinh vien de mo cong ra ngoai."
    }
    if (-not $isPingBlocked -and -not $isDnsBlocked -and -not $isWebBlocked -and -not $isSshBlocked) {
        $conclusions += "MANG TU DO (Full Internet Access): Mang mo hoan toan, khong co chinh sach chan dang ke."
    }
}

$results.Diagnosis = $conclusions

foreach ($c in $conclusions) {
    Write-Host "`n  [*] $c" -ForegroundColor Yellow
}

# -------------------------------------------------------------------------
# 7. XUAT BAO CAO THU THAP THONG TIN
# -------------------------------------------------------------------------
$timestampStr = (Get-Date).ToString("yyyyMMdd_HHmmss")
$reportJsonFile = Join-Path $OutputDir "network_audit_$timestampStr.json"
$reportTxtFile = Join-Path $OutputDir "network_audit_$timestampStr.txt"

# Luu file JSON
$results | ConvertTo-Json -Depth 6 | Set-Content -Path $reportJsonFile -Encoding UTF8

# Luu file TXT de doc
$txtSummary = @"
========================================================================
            BAO CAO THU THAP THONG TIN MANG (NETWORK AUDIT)
            Thoi gian: $($results.Timestamp)
========================================================================

1. THONG TIN MANG CUC BO:
   - Network Interface : $($results.LocalInfo.Interface)
   - IPv4 Cuc bo       : $($results.LocalInfo.IPv4)
   - Default Gateway   : $($results.LocalInfo.DefaultGateway)
   - DNS Servers       : $($results.LocalInfo.DNSServers)
   - System Proxy      : $(if ($results.LocalInfo.ProxyEnabled) { $results.LocalInfo.ProxyServer } else { "Khong bat" })

2. LAYER 3 (ICMP PING):
   - Ping Gateway (10.x / 192.168.x) : $(if ($results.Layer3_Egress.Gateway.Success) { "THONG" } else { "CHAN/TIMEOUT" })
   - Ping Google (8.8.8.8)           : $(if ($results.Layer3_Egress["8.8.8.8"].Success) { "THONG" } else { "CHAN/TIMEOUT" })
   - Ping Cloudflare (1.1.1.1)       : $(if ($results.Layer3_Egress["1.1.1.1"].Success) { "THONG" } else { "CHAN/TIMEOUT" })

3. LAYER 7 (DNS LOOKUP):
   - Phan giai google.com            : $($results.Layer7_DNS["google.com"].Status) ($($results.Layer7_DNS["google.com"].ResolvedIP))
   - Phan giai github.com            : $($results.Layer7_DNS["github.com"].Status) ($($results.Layer7_DNS["github.com"].ResolvedIP))
   - Phan giai usth.edu.vn           : $($results.Layer7_DNS["usth.edu.vn"].Status) ($($results.Layer7_DNS["usth.edu.vn"].ResolvedIP))
   - Direct Query 8.8.8.8:53         : $(if ($results.Layer7_DNS["Direct_8.8.8.8_Query"]) { "CHO PHEP" } else { "CHAN" })

4. LAYER 4 (TCP PORT REACHABILITY):
   - Port 80 (HTTP)                  : $(if ($results.Layer4_Ports["1.1.1.1:80"].Open) { "MO" } else { "CHAN" })
   - Port 443 (HTTPS)                : $(if ($results.Layer4_Ports["1.1.1.1:443"].Open) { "MO" } else { "CHAN" })
   - Port 22 (SSH)                   : $(if ($results.Layer4_Ports["github.com:22"].Open) { "MO" } else { "CHAN" })
   - Port 53 (DNS TCP)               : $(if ($results.Layer4_Ports["8.8.8.8:53"].Open) { "MO" } else { "CHAN" })
   - Tailscale DERP (443)            : $(if ($results.Layer4_Ports["derp1.tailscale.com:443"].Open) { "MO" } else { "CHAN" })
   - Port 8080 (Alt HTTP)            : $(if ($results.Layer4_Ports["1.1.1.1:8080"].Open) { "MO" } else { "CHAN" })

5. CAPTIVE PORTAL:
   - Phat hien chuyen huong          : $(if ($results.CaptivePortal.Detected) { "CO" } else { "KHONG" })
   - Chi tiet                        : $($results.CaptivePortal.Detail)

6. KET LUAN CHAN DOAN:
$($conclusions -join "`n")

========================================================================
"@

$txtSummary | Set-Content -Path $reportTxtFile -Encoding UTF8

Write-Host "`n" + ("=" * 74) -ForegroundColor DarkGray
Write-Host " [+] Da luu file bao cao JSON chi tiet tai : $reportJsonFile" -ForegroundColor Cyan
Write-Host " [+] Da luu file tom tat TXT tai           : $reportTxtFile" -ForegroundColor Cyan
Write-Host ("=" * 74) + "`n" -ForegroundColor DarkGray
