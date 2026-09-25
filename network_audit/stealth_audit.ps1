# =========================================================================
# STEALTH NETWORK AUDIT & PASSIVE INSPECTION ENGINE
# Thiet ke bao mat cao:
# 1. Zero GUI / Zero Console Output: Chay 100% ngam, khong in ky tu ra man hinh.
# 2. Passive First: Doc bang Route OS, khong phat goi tin neu la mang co lap.
# 3. Traffic Blending: Chi dung HTTPS (443) voi Chrome User-Agent, khong quet port la.
# 4. Luu ket qua tinh vao file cache de nguoi dung xem lai khi can.
# =========================================================================

$ErrorActionPreference = "SilentlyContinue"
$ProgressPreference = "SilentlyContinue"

$OutputDir = $PSScriptRoot
if (-not $OutputDir) { $OutputDir = (Get-Location).Path }

$logFileDat = Join-Path $OutputDir ".network_cache.dat"
$logFileTxt = Join-Path $OutputDir ".network_cache.txt"

$auditData = [ordered]@{
    Timestamp       = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Mode            = "Stealth Passive & Blended Egress"
    Interface       = "Unknown"
    IPv4            = "N/A"
    Gateway         = "N/A"
    DNSServers      = @()
    SystemProxy     = "None"
    HasDefaultRoute = $false
    DnsResolution   = "Untested"
    HttpEgress      = "Untested"
    HttpsEgress     = "Untested"
    CaptivePortal   = "Untested"
    Verdict         = "Undetermined"
    Details         = @()
}

# -------------------------------------------------------------------------
# GIAI DOAN 1: PASSIVE OS INSPECTION (0 BYTE RA MANG - KHONG THE BI PHAT HIEN)
# -------------------------------------------------------------------------
try {
    # 1. Tim route 0.0.0.0/0 co metric uu tien nhat
    $bestRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" | Sort-Object RouteMetric | Select-Object -First 1
    if ($bestRoute) {
        $auditData.HasDefaultRoute = $true
        $auditData.Gateway = $bestRoute.NextHop
        $adapter = Get-NetIPConfiguration -InterfaceAlias $bestRoute.InterfaceAlias -ErrorAction SilentlyContinue
    } else {
        $adapter = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } | Select-Object -First 1
        if ($adapter) {
            $auditData.HasDefaultRoute = $true
            $auditData.Gateway = $adapter.IPv4DefaultGateway.NextHop
        }
    }

    if ($adapter) {
        $auditData.Interface = $adapter.InterfaceAlias
        if ($adapter.IPv4Address) {
            $auditData.IPv4 = ($adapter.IPv4Address.IPAddress | Select-Object -First 1)
        }
        if ($adapter.DNSServer.ServerAddresses) {
            $auditData.DNSServers = @($adapter.DNSServer.ServerAddresses)
        }
    }

    # 2. Kiem tra System Proxy
    $proxyReg = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($proxyReg.ProxyEnable -eq 1 -and $proxyReg.ProxyServer) {
        $auditData.SystemProxy = $proxyReg.ProxyServer
    }
} catch {
    $auditData.Details += "Error in passive inspection: $($_.Exception.Message)"
}

# -------------------------------------------------------------------------
# GIAI DOAN 2: DANH GIA AIR-GAP TRUOC KHI EMIT PACKET
# -------------------------------------------------------------------------
if (-not $auditData.HasDefaultRoute) {
    # Khong co gateway ra ngoai -> Mang co lap hoan toan (Air-gapped Intranet)
    $auditData.Verdict = "AIR_GAPPED_INTRANET"
    $auditData.Details += "Khong co Default Route (0.0.0.0/0). Tuong lua co lap hoan toan trong mang LAN truong."
} else {
    # -------------------------------------------------------------------------
    # GIAI DOAN 3: TRAFFIC BLENDING (MO PHONG 100% TRINH DUYET CHROME)
    # -------------------------------------------------------------------------
    # Them do tre ngau nhien (Jitter 1 - 2s) de xoa chu ky may moc
    Start-Sleep -Milliseconds (Get-Random -Minimum 1000 -Maximum 2000)

    # 1. Thu phan giai DNS thong qua OS Resolver
    try {
        $dnsTest = Resolve-DnsName -Name "google.com" -Type A -QuickTimeout -ErrorAction SilentlyContinue
        if ($dnsTest -and $dnsTest.IPAddress) {
            $auditData.DnsResolution = "RESOLVED"
        } else {
            $auditData.DnsResolution = "FAILED_OR_BLOCKED"
        }
    } catch {
        $auditData.DnsResolution = "ERROR"
    }

    Start-Sleep -Milliseconds (Get-Random -Minimum 500 -Maximum 1200)

    # 2. Kiem tra HTTP chuan (Windows NCSI check)
    $chromeUA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    try {
        $httpReq = [System.Net.HttpWebRequest]::Create("http://www.msftconnecttest.com/connecttest.txt")
        $httpReq.UserAgent = $chromeUA
        $httpReq.Timeout = 4000
        $httpReq.AllowAutoRedirect = $false

        $httpResp = $httpReq.GetResponse()
        $statusCode = [int]$httpResp.StatusCode

        if ($statusCode -eq 200) {
            $auditData.HttpEgress = "OPEN"
            $auditData.CaptivePortal = "NONE"
        } elseif ($statusCode -eq 302 -or $statusCode -eq 301) {
            $auditData.HttpEgress = "INTERCEPTED"
            $auditData.CaptivePortal = "DETECTED_REDIRECT_LOGIN"
            $auditData.Details += "Redirect to: $($httpResp.Headers['Location'])"
        } else {
            $auditData.HttpEgress = "ABNORMAL_CODE_$statusCode"
        }
        $httpResp.Close()
    } catch [System.Net.WebException] {
        if ($_.Response) {
            $statusCode = [int]$_.Response.StatusCode
            if ($statusCode -eq 302 -or $statusCode -eq 301) {
                $auditData.HttpEgress = "INTERCEPTED"
                $auditData.CaptivePortal = "DETECTED_REDIRECT_LOGIN"
            }
        } else {
            $auditData.HttpEgress = "BLOCKED_OR_TIMEOUT"
        }
    } catch {
        $auditData.HttpEgress = "BLOCKED_OR_TIMEOUT"
    }

    Start-Sleep -Milliseconds (Get-Random -Minimum 500 -Maximum 1200)

    # 3. Kiem tra HTTPS 443 chuan (Handshake toi Cloudflare 1.1.1.1)
    try {
        $httpsReq = [System.Net.HttpWebRequest]::Create("https://1.1.1.1/")
        $httpsReq.UserAgent = $chromeUA
        $httpsReq.Timeout = 4000
        $httpsReq.AllowAutoRedirect = $false

        $httpsResp = $httpsReq.GetResponse()
        $auditData.HttpsEgress = "OPEN"
        $httpsResp.Close()
    } catch [System.Net.WebException] {
        if ($_.Response) {
            $auditData.HttpsEgress = "OPEN"
        } else {
            $auditData.HttpsEgress = "BLOCKED_OR_DROPPED"
        }
    } catch {
        $auditData.HttpsEgress = "BLOCKED_OR_DROPPED"
    }

    # -------------------------------------------------------------------------
    # KET LUAN MO HINH CHAN
    # -------------------------------------------------------------------------
    if ($auditData.CaptivePortal -like "DETECTED*") {
        $auditData.Verdict = "CAPTIVE_PORTAL_REQUIRED"
        $auditData.Details += "Mang dang bi chan o cong dang nhap Wi-Fi truong. Can dang nhap tai khoan de thong ra ngoai."
    } elseif ($auditData.HttpEgress -eq "OPEN" -and $auditData.HttpsEgress -eq "OPEN") {
        $auditData.Verdict = "FULL_INTERNET_ACCESS"
        $auditData.Details += "Mang mo hoan toan ra ngoai Internet. Khong co tuong lua chan."
    } elseif ($auditData.DnsResolution -eq "RESOLVED" -and $auditData.HttpsEgress -eq "BLOCKED_OR_DROPPED") {
        $auditData.Verdict = "FIREWALL_EGRESS_BLOCKED"
        $auditData.Details += "Phan giai duoc ten mien nhung tuong lua DROP toan bo goi tin ra cong 443 ngoai truong."
    } elseif ($auditData.DnsResolution -ne "RESOLVED" -and $auditData.HttpsEgress -eq "BLOCKED_OR_DROPPED") {
        $auditData.Verdict = "RESTRICTED_INTRANET_ISOLATED"
        $auditData.Details += "Mang noi bo truong co lap. Khong the ra ngoai Internet."
    } else {
        $auditData.Verdict = "PARTIAL_FILTERING"
        $auditData.Details += "Chinh sach mang han che mot phan."
    }
}

# -------------------------------------------------------------------------
# GIAI DOAN 4: LUU KET QUA TINH VAO FILE AN
# -------------------------------------------------------------------------
$auditData | ConvertTo-Json -Depth 5 | Set-Content -Path $logFileDat -Encoding UTF8

$humanSummary = @"
========================================================================
             STEALTH NETWORK AUDIT REPORT (CHE DO AN DANH)
             Thoi gian quet : $($auditData.Timestamp)
             Ket luan chinh : $($auditData.Verdict)
========================================================================

1. THONG SO THIET BI NOI BO (PASSIVE):
   - Card mang dang dung : $($auditData.Interface)
   - Dia chi IPv4        : $($auditData.IPv4)
   - Cong Default Gateway: $($auditData.Gateway)
   - May chu DNS noi bo  : $(($auditData.DNSServers) -join ", ")
   - Cau hinh Proxy OS   : $($auditData.SystemProxy)
   - Co Default Route    : $(if ($auditData.HasDefaultRoute) { "CO" } else { "KHONG (MANG CO LAP)" })

2. KET QUA LUU LUONG NGAM (MO PHONG DUYET WEB):
   - Phan giai ten mien (DNS) : $($auditData.DnsResolution)
   - Ket noi HTTP (Port 80)   : $($auditData.HttpEgress)
   - Ket noi HTTPS (Port 443) : $($auditData.HttpsEgress)
   - Canh bao Captive Portal  : $($auditData.CaptivePortal)

3. KET LUAN CHI TIET TUNG TRUONG HOP:
$(($auditData.Details) -join "`n")

========================================================================
"@

$humanSummary | Set-Content -Path $logFileTxt -Encoding UTF8
exit 0
