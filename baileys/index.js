const { default: makeWASocket, DisconnectReason, useMultiFileAuthState, downloadMediaMessage } = require('@whiskeysockets/baileys')
const qrcode = require('qrcode-terminal')
const axios  = require('axios')
const http   = require('http')

const FLASK_URL    = 'http://localhost:5000/message'
const BOT_START    = Math.floor(Date.now() / 1000)

let sock = null // global so /send endpoint can use it

// ── Simple HTTP server for Flask to call back into Baileys ────────────────────
const server = http.createServer(async (req, res) => {
    if (req.method === 'POST' && req.url === '/send') {
        let body = ''
        req.on('data', chunk => body += chunk)
        req.on('end', async () => {
            try {
                const { to, message } = JSON.parse(body)
                if (sock && to && message) {
                    await sock.sendMessage(to, { text: message })
                    res.writeHead(200)
                    res.end('ok')
                } else {
                    res.writeHead(400)
                    res.end('missing fields or not connected')
                }
            } catch (e) {
                res.writeHead(500)
                res.end(e.message)
            }
        })
    } else {
        res.writeHead(404)
        res.end()
    }
})

server.listen(3001, () => console.log('[BAILEYS] Send server listening on :3001'))

// ── Message splitter ──────────────────────────────────────────────────────────
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

// ── Main bot ──────────────────────────────────────────────────────────────────
async function startBot() {
    const { state, saveCreds } = await useMultiFileAuthState('./auth_info')

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        getMessage: async () => ({ conversation: '' }),
        mediaUploadTimeoutMs: 120000
    })

    sock.ev.on('creds.update', saveCreds)

    sock.ev.on('connection.update', ({ connection, lastDisconnect, qr }) => {
        if (qr) {
            console.log('\n📱 Scan this QR code with WhatsApp:\n')
            qrcode.generate(qr, { small: true })
        }
        if (connection === 'close') {
            const code = lastDisconnect?.error?.output?.statusCode
            if (code !== DisconnectReason.loggedOut) {
                console.log('[BAILEYS] Reconnecting...')
                startBot()
            } else {
                console.log('[BAILEYS] Logged out. Delete auth_info folder and restart.')
            }
        }
        if (connection === 'open') {
            console.log('[BAILEYS] ✅ MAX∞ is live on WhatsApp!')
        }
    })

    sock.ev.on('messages.upsert', async ({ messages, type }) => {
        if (type !== 'notify') return

        for (const msg of messages) {
            if (msg.key.fromMe) continue

            // Skip status updates and broadcasts
            if (chatId === 'status@broadcast' || chatId === 'status@s.whatsapp.net') continue
            if (chatId.endsWith('@broadcast')) continue

            // Skip old/history messages
            const msgTime = msg.messageTimestamp
            if (msgTime && msgTime < BOT_START - 10) continue

            const chatId = msg.key.remoteJid
            const isGroup = chatId.endsWith('@g.us')

            // For direct chats, remoteJid IS the real phone number (e.g. 2348163958919@s.whatsapp.net)
            // For group chats, participant is the sender
            let sender = isGroup
                ? (msg.key.participant || chatId)
                : chatId

            // Strip device suffix e.g. 2348163958919:27@s.whatsapp.net → 2348163958919@s.whatsapp.net
            if (sender.includes(':') && sender.includes('@')) {
                const parts = sender.split('@')
                sender = parts[0].split(':')[0] + '@' + parts[1]
            }

            // Use chatId as the canonical ID for direct chats (always has real number)
            const canonicalId = isGroup ? sender : chatId.split(':')[0].split('@')[0] + '@s.whatsapp.net'

            console.log(`[MSG] chatId=${chatId} sender=${sender} canonical=${canonicalId}`)

            try {
                let payload = { sender: canonicalId, chatId, type: 'text', text: '', name: msg.pushName || '' }

                if (msg.message?.conversation) {
                    payload.text = msg.message.conversation

                } else if (msg.message?.extendedTextMessage) {
                    payload.text = msg.message.extendedTextMessage.text

                } else if (msg.message?.imageMessage) {
                    const buf = await downloadMediaMessage(msg, 'buffer', {})
                    payload.type      = 'image'
                    payload.image_b64 = buf.toString('base64')
                    payload.text      = msg.message.imageMessage.caption || ''

                } else if (msg.message?.audioMessage || msg.message?.pttMessage) {
                    // Voice notes
                    const buf = await downloadMediaMessage(msg, 'buffer', {})
                    payload.type      = 'audio'
                    payload.audio_b64 = buf.toString('base64')
                    payload.text      = ''

                } else if (msg.message?.documentMessage) {
                    const buf = await downloadMediaMessage(msg, 'buffer', {})
                    payload.type      = 'document'
                    payload.file_b64  = buf.toString('base64')
                    payload.file_name = msg.message.documentMessage.fileName || 'file'
                    payload.text      = msg.message.documentMessage.caption || ''

                } else {
                    console.log('[MSG] unsupported type, skipping')
                    continue
                }

                const res    = await axios.post(FLASK_URL, payload, { timeout: 120000 })
                const result = res.data

                if (result.type === 'image' && result.image_bytes) {
                    const imgBuf = Buffer.from(result.image_bytes, 'base64')
                    await sock.sendMessage(chatId, {
                        image:   imgBuf,
                        caption: result.caption || '✨'
                    })
                    console.log('[SEND] image sent')

                } else if (result.reply) {
                    const chunks = splitMessage(result.reply)
                    for (const chunk of chunks) {
                        await sock.sendMessage(chatId, { text: chunk })
                    }
                    console.log(`[SEND] ${chunks.length} chunk(s)`)
                }

            } catch (err) {
                console.error('[ERROR]', err.message)
                try {
                    await sock.sendMessage(chatId, { text: "Something went wrong on my end. Try again in a moment." })
                } catch (_) {}
            }
        }
    })
}

console.log('Starting MAX∞...')
startBot()