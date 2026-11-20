package com.cctr.export

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.cctr.export.ui.CctrMinimalTheme
import com.cctr.export.ui.MainScreen
import com.cctr.export.ui.MainViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            CctrMinimalTheme {
                val vm: MainViewModel = viewModel()
                MainScreen(vm)
            }
        }
    }
}
