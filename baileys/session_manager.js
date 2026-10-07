const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, downloadMediaMessage } = require('@whiskeysockets/baileys')
const path = require('path')
const fs = require('fs')
const axios = require('axios')
const qrcode = require('qrcode-terminal')

const SESSIONS_DIR = path.join(__dirname, 'sessions')
if (!fs.existsSync(SESSIONS_DIR)) {
    fs.mkdirSync(SESSIONS_DIR, { recursive: true })
}

// Auto-migrate old single-tenant auth_info if present
const OLD_AUTH_DIR = path.join(__dirname, 'auth_info')
const MAIN_AUTH_DIR = path.join(SESSIONS_DIR, 'main', 'auth_info')
if (fs.existsSync(OLD_AUTH_DIR) && !fs.existsSync(MAIN_AUTH_DIR)) {
    try {
        fs.mkdirSync(path.join(SESSIONS_DIR, 'main'), { recursive: true })
        fs.renameSync(OLD_AUTH_DIR, MAIN_AUTH_DIR)
        console.log('[MIGRATION] Migrated legacy auth_info to sessions/main/auth_info')
    } catch (e) {
        console.error('[MIGRATION ERROR]', e.message)
    }
}

const FLASK_URL = process.env.FLASK_URL || 'http://localhost:5000/message'
const BOT_START = Math.floor(Date.now() / 1000)

function splitMessage(text, limit = 1500) {
    const chunks = []
    while (text.length > limit) {
        let cut = text.lastIndexOf('\n', limit)
        if (cut === -1) cut = limit
        chunks.push(text.slice(0, cut).trim())
        text = text.slice(cut).trim()
    }
    if (text) chunks.push(text)
    return chunks
}

class SessionManager {
    constructor() {
        this.sessions = new Map() // tenantId -> { sock, status, qr, pairingCode, phone, reconnectAttempts, manualStop }
        this.humanTakeover = new Map() // key: `${tenantId}:${chatId}` -> timestamp
        this.chatRateLimits = new Map() // key: canonicalId -> array of timestamps
    }

    recordHumanActivity(tenantId, chatId, durationMs = 30 * 60 * 1000) {
        const key = `${tenantId}:${chatId}`
        this.humanTakeover.set(key, Date.now() + durationMs)
        console.log(`[HUMAN TAKEOVER] Human activity detected on [${tenantId}] in ${chatId}. AI will stay silent for ${durationMs / 60000} mins.`)
    }

    isHumanTakeoverActive(tenantId, chatId) {
        const key = `${tenantId}:${chatId}`
        const expiry = this.humanTakeover.get(key)
        if (!expiry) return false
        if (Date.now() < expiry) {
            return true
        }
        this.humanTakeover.delete(key)
        return false
    }

    clearHumanTakeover(tenantId, chatId) {
        const key = `${tenantId}:${chatId}`
        this.humanTakeover.delete(key)
        console.log(`[HUMAN TAKEOVER] Cleared takeover for [${tenantId}] in ${chatId}. AI is active.`)
    }

    getSession(tenantId) {
        return this.sessions.get(tenantId)
    }

    getAllSessions() {
        const list = []
        for (const [tenantId, s] of this.sessions.entries()) {
            list.push({
                tenant_id: tenantId,
                status: s.status,
                phone: s.phone || null,
                pairing_code: s.pairingCode || null,
                has_qr: !!s.qr,
                reconnect_attempts: s.reconnectAttempts || 0,
                connected_at: s.connectedAt || null
            })
        }
        return list
    }

    getAuthDir(tenantId) {
        const dir = path.join(SESSIONS_DIR, tenantId, 'auth_info')
        if (!fs.existsSync(dir)) {
            fs.mkdirSync(dir, { recursive: true })
        }
        return dir
    }

    async initSession(tenantId, options = {}) {
        const { phoneNumber = null, forcePairingCode = false } = options

        if (this.sessions.has(tenantId)) {
            const current = this.sessions.get(tenantId)
            if (current.status === 'connected') {
                console.log(`[SESSION] ${tenantId} is already connected`)
                return current
            }
        }

        const authDir = this.getAuthDir(tenantId)
        const { state, saveCreds } = await useMultiFileAuthState(authDir)

        const sessionState = {
            tenantId,
            sock: null,
            status: 'initializing',
            qr: null,
            pairingCode: null,
            phone: phoneNumber ? phoneNumber.replace(/\D/g, '') : null,
            reconnectAttempts: 0,
            manualStop: false,
            connectedAt: null
        }

        this.sessions.set(tenantId, sessionState)

        const sock = makeWASocket({
            auth: state,
            printQRInTerminal: false,
            getMessage: async () => ({ conversation: '' }),
            mediaUploadTimeoutMs: 120000
        })

        sessionState.sock = sock

        sock.ev.on('creds.update', saveCreds)

        // Handle pairing code request if phone number is supplied and socket is not yet registered
        if ((forcePairingCode || phoneNumber) && sessionState.phone) {
            setTimeout(async () => {
                try {
                    if (sock.authState?.creds && !sock.authState.creds.registered) {
                        const cleanPhone = sessionState.phone
                        console.log(`[PAIRING] Requesting pairing code for tenant ${tenantId} (Phone: ${cleanPhone})...`)
                        const code = await sock.requestPairingCode(cleanPhone)
                        sessionState.pairingCode = code
                        sessionState.status = 'pairing_ready'
                        console.log(`\n══════════════════════════════════════════`)
                        console.log(`  📱 [${tenantId.toUpperCase()}] PAIRING CODE: ${code}`)
                        console.log(`══════════════════════════════════════════\n`)
                    }
                } catch (err) {
                    console.error(`[PAIRING ERROR] Tenant ${tenantId}:`, err.message)
                }
            }, 3000)
        }

        // Connection events
        sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
            if (qr) {
                sessionState.qr = qr
                sessionState.status = 'qr_ready'
                console.log(`[SESSION] Tenant ${tenantId}: QR Code generated`)
            }

            if (connection === 'open') {
                sessionState.status = 'connected'
                sessionState.qr = null
                sessionState.pairingCode = null
                sessionState.reconnectAttempts = 0
                sessionState.connectedAt = new Date().toISOString()
                console.log(`[SESSION] ✅ Tenant [${tenantId}] is live on WhatsApp!`)
            }

            if (connection === 'close') {
                const code = lastDisconnect?.error?.output?.statusCode
                console.log(`[SESSION] Tenant [${tenantId}] connection closed (code: ${code})`)
                sessionState.status = 'disconnected'

                if (sessionState.manualStop) {
                    console.log(`[SESSION] Tenant [${tenantId}] stopped manually.`)
                    return
                }

                if (code === DisconnectReason.loggedOut) {
                    console.log(`[SESSION] Tenant [${tenantId}] logged out. Cleaning credentials.`)
                    try {
                        fs.rmSync(authDir, { recursive: true, force: true })
                    } catch (_) {}
                    sessionState.status = 'logged_out'
                } else {
                    sessionState.reconnectAttempts = (sessionState.reconnectAttempts || 0) + 1
                    const delay = Math.min(sessionState.reconnectAttempts * 4000, 30000)
                    console.log(`[SESSION] Tenant [${tenantId}] reconnecting in ${delay / 1000}s (attempt ${sessionState.reconnectAttempts})...`)
                    setTimeout(() => {
                        this.initSession(tenantId, { phoneNumber: sessionState.phone })
                    }, delay)
                }
            }
        })

        // Incoming call rejection
        sock.ev.on('call', async (calls) => {
            for (const call of calls) {
                if (call.status === 'offer') {
                    console.log(`[CALL] Tenant [${tenantId}] incoming call from ${call.from}`)
                    try {
                        await sock.rejectCall(call.id, call.from)
                        await sock.sendMessage(call.from, {
                            text: `Hey! 👋 I cannot take live voice calls inside WhatsApp directly, but feel free to send a text or voice note and I will reply right away!`
                        })
                    } catch (err) {
                        console.error('[CALL ERROR]', err.message)
                    }
                }
            }
        })

        // Messages handler
        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') return

            for (const msg of messages) {
                const chatId = msg.key.remoteJid
                if (!chatId) continue

                // ── 1. Human Activity & Takeover Commands (Sent from Charles's phone) ──
                if (msg.key.fromMe) {
                    const text = (msg.message?.conversation || msg.message?.extendedTextMessage?.text || '').trim().toLowerCase()
                    if (text === '!ai resume' || text === '!resume') {
                        this.clearHumanTakeover(tenantId, chatId)
                    } else if (text === '!ai pause' || text === '!pause') {
                        this.recordHumanActivity(tenantId, chatId, 24 * 60 * 60 * 1000) // 24hr mute
                    } else {
                        // Charles is actively speaking with this customer:
                        // Quiet the AI for 30 minutes so Charles can talk uninterrupted!
                        this.recordHumanActivity(tenantId, chatId, 30 * 60 * 1000)
                    }
                    continue
                }

                // ── 2. Strictly 1-on-1 Direct Messages Only (@s.whatsapp.net) ──────────
                // ZERO INTERFERENCE IN GROUPS & BROADCASTS:
                // Completely drops:
                // - All Group chats (@g.us)
                // - All Community member / hidden identity chats (@lid)
                // - All Status broadcasts (@broadcast, status@...)
                // - All Newsletters / Channels (@newsletter)
                // - Any message with participant or msg.key.participant populated (group indicator)
                // - Any chat where remoteJid does not cleanly end with @s.whatsapp.net
                const rawJid = (chatId || '').toLowerCase()
                const isGroupOrBroadcast = rawJid.includes('@g.us') ||
                                           rawJid.includes('@lid') ||
                                           rawJid.includes('@broadcast') ||
                                           rawJid.includes('@newsletter') ||
                                           !rawJid.endsWith('@s.whatsapp.net') ||
                                           !!msg.key?.participant ||
                                           !!msg.participant

                if (isGroupOrBroadcast) {
                    // Silently drop - Business and assistant bots NEVER touch group chats!
                    continue
                }

                // ── 3. Check Live Human Takeover (Zero Interference Guard) ─────────────
                if (this.isHumanTakeoverActive(tenantId, chatId)) {
                    console.log(`[ZERO-INTERFERENCE] [${tenantId}] Human active in ${chatId}. AI will NOT reply.`)
                    continue
                }

                const msgTime = msg.messageTimestamp
                if (msgTime && msgTime < BOT_START - 10) continue

                let sender = chatId
                if (sender.includes(':') && sender.includes('@')) {
                    const parts = sender.split('@')
                    sender = parts[0].split(':')[0] + '@' + parts[1]
                }

                const canonicalId = chatId.split(':')[0].split('@')[0] + '@s.whatsapp.net'
                const cleanDigits = canonicalId.split('@')[0].replace(/\D/g, '')

                // ── 4. Cross-Bot Loop Guard (Never reply to ANY bot in the fleet) ──────
                const FLEET_NUMBERS = [
                    '2348163958919', // Joseph / MAX Central line
                    '2347017284810', // Campos
                    '2348108395401', // Portal Consult
                    '2349068942140'  // Princess / Eby Beauty
                ]
                for (const s of this.sessions.values()) {
                    if (s.phone && !FLEET_NUMBERS.includes(s.phone)) {
                        FLEET_NUMBERS.push(s.phone)
                    }
                }

                if (FLEET_NUMBERS.includes(cleanDigits)) {
                    console.log(`[LOOP GUARD] [${tenantId}] Dropping message from fleet number: ${cleanDigits}`)
                    continue
                }

                // ── 5. Rapid-Fire / Anti-Spam Breaker per chat ────────────────────────
                const now = Date.now()
                const recentTimes = (this.chatRateLimits.get(canonicalId) || []).filter(t => now - t < 15000)
                if (recentTimes.length >= 3) {
                    console.warn(`[SPAM BREAKER] [${tenantId}] Rapid messages from ${canonicalId}. Cooldown 5 mins.`)
                    this.recordHumanActivity(tenantId, chatId, 5 * 60 * 1000)
                    continue
                }
                recentTimes.push(now)
                this.chatRateLimits.set(canonicalId, recentTimes)

                console.log(`[MSG] [${tenantId}] chatId=${chatId} sender=${sender}`)

                try {
                    let payload = {
                        tenant_id: tenantId,
                        sender: canonicalId,
                        chatId,
                        type: 'text',
                        text: '',
                        name: msg.pushName || ''
                    }

                    if (msg.message?.conversation) {
                        payload.text = msg.message.conversation
                    } else if (msg.message?.extendedTextMessage) {
                        payload.text = msg.message.extendedTextMessage.text
                    } else if (msg.message?.imageMessage) {
                        const buf = await downloadMediaMessage(msg, 'buffer', {})
                        payload.type = 'image'
                        payload.image_b64 = buf.toString('base64')
                        payload.text = msg.message.imageMessage.caption || ''
                    } else if (msg.message?.audioMessage || msg.message?.pttMessage) {
                        const buf = await downloadMediaMessage(msg, 'buffer', {})
                        payload.type = 'audio'
                        payload.audio_b64 = buf.toString('base64')
                        payload.text = ''
                    } else if (msg.message?.documentMessage) {
                        const buf = await downloadMediaMessage(msg, 'buffer', {})
                        payload.type = 'document'
                        payload.file_b64 = buf.toString('base64')
                        payload.file_name = msg.message.documentMessage.fileName || 'file'
                        payload.text = msg.message.documentMessage.caption || ''
                    } else {
                        continue
                    }

                    // Forward to Flask Multi-Tenant message processor
                    const res = await axios.post(FLASK_URL, payload, { timeout: 120000 })
                    const result = res.data

                    await this.dispatchResponse(tenantId, chatId, result)

                } catch (err) {
                    console.error(`[PROCESS ERROR] [${tenantId}]`, err.message)
                }
            }
        })

        return sessionState
    }

    async dispatchResponse(tenantId, chatId, result) {
        const session = this.sessions.get(tenantId)
        if (!session || !session.sock) return
        const sock = session.sock

        // 1. Multiple Guide Images (e.g. Campos Walkthroughs)
        if (Array.isArray(result.images) && result.images.length > 0) {
            for (const imgItem of result.images) {
                const imgBuf = Buffer.from(imgItem.image_bytes, 'base64')
                await sock.sendMessage(chatId, {
                    image: imgBuf,
                    caption: imgItem.caption || ''
                })
            }
        }

        // 2. Single Voice Reply
        if (result.type === 'audio' && result.audio_bytes) {
            const audioBuf = Buffer.from(result.audio_bytes, 'base64')
            const isOgg = audioBuf.slice(0, 4).toString() === 'OggS'
            await sock.sendMessage(chatId, {
                audio: audioBuf,
                mimetype: isOgg ? 'audio/ogg; codecs=opus' : 'audio/mpeg',
                ptt: isOgg ? true : false
            })
            if (result.caption) {
                await sock.sendMessage(chatId, { text: result.caption })
            }
        }
        // 3. Single Sticker
        else if (result.type === 'sticker' && result.sticker_bytes) {
            const stickerBuf = Buffer.from(result.sticker_bytes, 'base64')
            await sock.sendMessage(chatId, { sticker: stickerBuf })
        }
        // 4. Single Image
        else if (result.type === 'image' && result.image_bytes) {
            const imgBuf = Buffer.from(result.image_bytes, 'base64')
            await sock.sendMessage(chatId, {
                image: imgBuf,
                caption: result.caption || '✨'
            })
        }
        // 5. Standard Text Reply
        if (result.reply) {
            const chunks = splitMessage(result.reply)
            for (const chunk of chunks) {
                await sock.sendMessage(chatId, { text: chunk })
            }
        }
    }

    async sendToRecipient(tenantId, to, options) {
        let session = this.sessions.get(tenantId)
        if (!session && tenantId === 'default') {
            // Pick first connected session
            for (const s of this.sessions.values()) {
                if (s.status === 'connected') {
                    session = s
                    break
                }
            }
        }

        if (!session || !session.sock) {
            throw new Error(`Session for tenant '${tenantId}' is not connected`)
        }

        const sock = session.sock
        const { message, type, audio_bytes, image_bytes, sticker_bytes, images } = options

        if (Array.isArray(images) && images.length > 0) {
            for (const item of images) {
                const buf = Buffer.from(item.image_bytes, 'base64')
                await sock.sendMessage(to, { image: buf, caption: item.caption || '' })
            }
            return { ok: true }
        }

        if (type === 'audio' && audio_bytes) {
            const audioBuf = Buffer.from(audio_bytes, 'base64')
            const isOgg = audioBuf.slice(0, 4).toString() === 'OggS'
            await sock.sendMessage(to, {
                audio: audioBuf,
                mimetype: isOgg ? 'audio/ogg; codecs=opus' : 'audio/mpeg',
                ptt: isOgg ? true : false
            })
        } else if (type === 'sticker' && sticker_bytes) {
            const stickerBuf = Buffer.from(sticker_bytes, 'base64')
            await sock.sendMessage(to, { sticker: stickerBuf })
        } else if (type === 'image' && image_bytes) {
            const imgBuf = Buffer.from(image_bytes, 'base64')
            await sock.sendMessage(to, { image: imgBuf, caption: message || '' })
        } else if (message) {
            const chunks = splitMessage(message)
            for (const chunk of chunks) {
                await sock.sendMessage(to, { text: chunk })
            }
        }

        return { ok: true }
    }

    async disconnectSession(tenantId) {
        const session = this.sessions.get(tenantId)
        if (!session) return { ok: false, error: 'Session not found' }
        session.manualStop = true
        if (session.sock) {
            try {
                session.sock.end(new Error('Manual disconnect'))
            } catch (_) {}
        }
        session.status = 'disconnected'
        return { ok: true }
    }

    async deleteSession(tenantId) {
        await this.disconnectSession(tenantId)
        this.sessions.delete(tenantId)
        const dir = path.join(SESSIONS_DIR, tenantId)
        try {
            if (fs.existsSync(dir)) {
                fs.rmSync(dir, { recursive: true, force: true })
            }
        } catch (e) {
            console.error('[DELETE ERROR]', e.message)
        }
        return { ok: true }
    }

    async autoRestoreSessions() {
        console.log('[SESSION MGR] Scanning for existing tenant sessions...')
        if (!fs.existsSync(SESSIONS_DIR)) return

        const entries = fs.readdirSync(SESSIONS_DIR, { withFileTypes: true })
        for (const entry of entries) {
            if (entry.isDirectory()) {
                const tenantId = entry.name
                const credsFile = path.join(SESSIONS_DIR, tenantId, 'auth_info', 'creds.json')
                if (fs.existsSync(credsFile)) {
                    console.log(`[SESSION MGR] Auto-restoring saved session for tenant: ${tenantId}`)
                    try {
                        await this.initSession(tenantId)
                    } catch (e) {
                        console.error(`[SESSION RESTORE ERROR] [${tenantId}]:`, e.message)
                    }
                }
            }
        }
    }
}

module.exports = new SessionManager()
