package com.endless.liftlog.data.backup

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import androidx.core.content.edit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.FileNotFoundException
import java.io.IOException
import java.io.OutputStream

/** The spreadsheet that backups are written to. */
data class BackupTarget(val uri: String, val name: String)

data class BackupStatus(
    val target: BackupTarget? = null,
    /** Update the backup file automatically after every finished workout. */
    val autoBackup: Boolean = true,
    val lastBackupAt: Long? = null,
    val lastError: String? = null,
    val inProgress: Boolean = false,
)

/**
 * Writes Excel backups to a file the user picks (Downloads, Google Drive, …) through the system
 * file picker, remembers that file so later backups update it, and restores from a file.
 * The app itself never touches the network.
 */
class BackupManager(
    context: Context,
    private val repository: BackupRepository,
    private val scope: CoroutineScope,
) {
    private val context = context.applicationContext
    private val prefs = this.context.getSharedPreferences("backup", Context.MODE_PRIVATE)
    private val mutex = Mutex()
    private val _status = MutableStateFlow(load())
    val status: StateFlow<BackupStatus> = _status.asStateFlow()

    /** Backs up into a file the user just created in the picker and remembers it. */
    suspend fun backupToNewFile(uri: Uri): Result<Unit> {
        runCatching {
            context.contentResolver.takePersistableUriPermission(
                uri,
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        }
        val result = write(uri)
        if (result.isSuccess) {
            val target = BackupTarget(uri.toString(), displayName(uri) ?: "LiftLog backup.xlsx")
            save { it.copy(target = target) }
        }
        return result
    }

    /** Overwrites the remembered backup file with the current data. */
    suspend fun updateBackup(): Result<Unit> {
        val target = _status.value.target
            ?: return Result.failure(IllegalStateException("Choose where to save the backup first"))
        return write(Uri.parse(target.uri))
    }

    /** Called after a workout is finished; runs in the background so navigation isn't held up. */
    fun autoBackupAfterWorkout() {
        val status = _status.value
        if (status.autoBackup && status.target != null) scope.launch { updateBackup() }
    }

    suspend fun readBackup(uri: Uri): Result<ParsedBackup> = withContext(Dispatchers.IO) {
        runCatching {
            val input = context.contentResolver.openInputStream(uri)
                ?: throw IOException("Couldn't open the file")
            input.use { BackupFormat.fromSheets(Xlsx.read(it)) }
        }
    }

    suspend fun restore(data: BackupData): Result<RestoreResult> = withContext(Dispatchers.IO) {
        mutex.withLock { runCatching { repository.replaceAll(data) } }
    }

    fun setAutoBackup(enabled: Boolean) = save { it.copy(autoBackup = enabled) }

    fun forgetTarget() {
        _status.value.target?.let { target ->
            runCatching {
                context.contentResolver.releasePersistableUriPermission(
                    Uri.parse(target.uri),
                    Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
                )
            }
        }
        save { it.copy(target = null, lastError = null) }
    }

    fun fileName(uri: Uri): String? = displayName(uri)

    private suspend fun write(uri: Uri): Result<Unit> = mutex.withLock {
        _status.update { it.copy(inProgress = true) }
        val result = withContext(Dispatchers.IO) {
            runCatching {
                val bytes = Xlsx.toBytes(BackupFormat.toSheets(repository.snapshot()))
                openForWrite(uri).use { it.write(bytes) }
            }
        }
        _status.update { it.copy(inProgress = false) }
        result.fold(
            onSuccess = { save { it.copy(lastBackupAt = System.currentTimeMillis(), lastError = null) } },
            onFailure = { error -> save { it.copy(lastError = describe(error)) } },
        )
        result.exceptionOrNull()?.let { Result.failure<Unit>(IOException(describe(it), it)) } ?: Result.success(Unit)
    }

    /** "wt" truncates the old content; not every provider supports it, so fall back in order. */
    private fun openForWrite(uri: Uri): OutputStream {
        var last: Exception? = null
        for (mode in listOf("wt", "rwt", "w")) {
            try {
                context.contentResolver.openOutputStream(uri, mode)?.let { return it }
            } catch (e: SecurityException) {
                throw e
            } catch (e: Exception) {
                last = e
            }
        }
        throw last ?: IOException("Couldn't write to the backup file")
    }

    private fun describe(error: Throwable): String = when (error) {
        is SecurityException -> "LiftLog no longer has access to the backup file. Choose it again."
        is FileNotFoundException -> "The backup file was moved or deleted. Choose a new file."
        else -> error.message ?: "Backup failed"
    }

    private fun displayName(uri: Uri): String? = runCatching {
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
            if (cursor.moveToFirst()) cursor.getString(0) else null
        }
    }.getOrNull()

    private fun load(): BackupStatus {
        val uri = prefs.getString(KEY_URI, null)
        return BackupStatus(
            target = uri?.let { BackupTarget(it, prefs.getString(KEY_NAME, null) ?: "LiftLog backup.xlsx") },
            autoBackup = prefs.getBoolean(KEY_AUTO, true),
            lastBackupAt = prefs.getLong(KEY_LAST, 0L).takeIf { it > 0L },
            lastError = prefs.getString(KEY_ERROR, null),
        )
    }

    private fun save(transform: (BackupStatus) -> BackupStatus) {
        _status.update(transform)
        val s = _status.value
        prefs.edit {
            putString(KEY_URI, s.target?.uri)
            putString(KEY_NAME, s.target?.name)
            putBoolean(KEY_AUTO, s.autoBackup)
            putLong(KEY_LAST, s.lastBackupAt ?: 0L)
            putString(KEY_ERROR, s.lastError)
        }
    }

    companion object {
        const val MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        private const val KEY_URI = "uri"
        private const val KEY_NAME = "name"
        private const val KEY_AUTO = "auto"
        private const val KEY_LAST = "last"
        private const val KEY_ERROR = "error"
    }
}
