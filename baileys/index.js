const express = require('express')
const cors = require('cors')
const sessionManager = require('./session_manager')

const app = express()
app.use(cors())
app.use(express.json({ limit: '50mb' }))

const PORT = process.env.PORT || 3001

// ── Health & Diagnostics ──────────────────────────────────────────────────────
app.get('/health', (req, res) => {
    const sessions = sessionManager.getAllSessions()
    const connected = sessions.filter(s => s.status === 'connected')
    res.json({
        status: 'ok',
        service: 'baileys-multi-tenant',
        total_sessions: sessions.length,
        connected_count: connected.length,
        sessions
    })
})

// ── List All Sessions ─────────────────────────────────────────────────────────
app.get('/sessions', (req, res) => {
    res.json({
        status: 'ok',
        sessions: sessionManager.getAllSessions()
    })
})

// ── Get Single Session Details ────────────────────────────────────────────────
app.get('/sessions/:tenant_id', (req, res) => {
    const tenantId = req.params.tenant_id
    const session = sessionManager.getSession(tenantId)
    if (!session) {
        return res.status(404).json({ status: 'error', message: 'Session not found' })
    }
    res.json({
        status: 'ok',
        tenant_id: tenantId,
        status_text: session.status,
        phone: session.phone,
        pairing_code: session.pairingCode,
        has_qr: !!session.qr,
        qr: session.qr || null,
        reconnect_attempts: session.reconnectAttempts || 0,
        connected_at: session.connectedAt || null
    })
})

// ── Initialize a Session ─────────────────────────────────────────────────────
app.post('/sessions/:tenant_id/init', async (req, res) => {
    const tenantId = req.params.tenant_id
    const { phone_number } = req.body || {}
    try {
        const session = await sessionManager.initSession(tenantId, {
            phoneNumber: phone_number
        })
        res.json({
            status: 'ok',
            tenant_id: tenantId,
            state: session.status
        })
    } catch (err) {
        res.status(500).json({ status: 'error', message: err.message })
    }
})

// ── Request 8-Digit Pairing Code ─────────────────────────────────────────────
app.post('/sessions/:tenant_id/pair-code', async (req, res) => {
    const tenantId = req.params.tenant_id
    const { phone_number } = req.body || {}
    if (!phone_number) {
        return res.status(400).json({ status: 'error', message: 'phone_number is required' })
    }

    const cleanPhone = phone_number.replace(/\D/g, '')

    try {
        await sessionManager.initSession(tenantId, {
            phoneNumber: cleanPhone,
            forcePairingCode: true
        })

        // Wait up to 5 seconds for pairing code to generate
        let code = null
        for (let i = 0; i < 10; i++) {
            await new Promise(r => setTimeout(r, 500))
            const session = sessionManager.getSession(tenantId)
            if (session && session.pairingCode) {
                code = session.pairingCode
                break
            }
            if (session && session.status === 'connected') {
                return res.json({ status: 'already_connected', tenant_id: tenantId })
            }
        }

        if (code) {
            return res.json({
                status: 'ok',
                tenant_id: tenantId,
                pairing_code: code,
                instructions: 'On client phone: WhatsApp > Linked Devices > Link with phone number instead > Enter code'
            })
        }

        res.json({
            status: 'pending',
            tenant_id: tenantId,
            message: 'Pairing code is generating. Please query /sessions/' + tenantId + ' in a few seconds.'
        })

    } catch (err) {
        res.status(500).json({ status: 'error', message: err.message })
    }
})

// ── Send Message on Specific Tenant Socket ───────────────────────────────────
app.post('/sessions/:tenant_id/send', async (req, res) => {
    const tenantId = req.params.tenant_id
    const { to, message, type, audio_bytes, image_bytes, sticker_bytes, images, caption } = req.body || {}

    if (!to) {
        return res.status(400).json({ status: 'error', message: 'Recipient "to" is required' })
    }

    try {
        await sessionManager.sendToRecipient(tenantId, to, {
            message,
            type,
            audio_bytes,
            image_bytes,
            sticker_bytes,
            images,
            caption
        })
        res.json({ status: 'ok', tenant_id: tenantId })
    } catch (err) {
        res.status(500).json({ status: 'error', message: err.message })
    }
})

// ── Legacy Send Endpoint (Sends using default/main connected session) ────────
app.post('/send', async (req, res) => {
    const { to, message, type, audio_bytes, image_bytes, sticker_bytes, images, caption, tenant_id } = req.body || {}
    const targetTenant = tenant_id || 'main'

    if (!to) {
        return res.status(400).json({ status: 'error', message: 'Recipient "to" is required' })
    }

    try {
        await sessionManager.sendToRecipient(targetTenant, to, {
            message,
            type,
            audio_bytes,
            image_bytes,
            sticker_bytes,
            images,
            caption
        })
        res.json({ status: 'ok' })
    } catch (err) {
        res.status(500).json({ status: 'error', message: err.message })
    }
})

// ── Disconnect Session ────────────────────────────────────────────────────────
app.post('/sessions/:tenant_id/disconnect', async (req, res) => {
    const tenantId = req.params.tenant_id
    const result = await sessionManager.disconnectSession(tenantId)
    res.json(result)
})

// ── Delete Session (Purges Auth Data) ─────────────────────────────────────────
app.post('/sessions/:tenant_id/delete', async (req, res) => {
    const tenantId = req.params.tenant_id
    const result = await sessionManager.deleteSession(tenantId)
    res.json(result)
})

// ── Start Server & Hydrate Saved Sessions ─────────────────────────────────────
app.listen(PORT, async () => {
    console.log(`\n==================================================`)
    console.log(`  MAX∞ Multi-Session Gateway listening on :${PORT}`)
    console.log(`==================================================\n`)

    // Automatically revive any previously connected sessions on disk
    await sessionManager.autoRestoreSessions()
})