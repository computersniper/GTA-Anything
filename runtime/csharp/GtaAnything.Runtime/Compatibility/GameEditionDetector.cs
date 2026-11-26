using System;
using System.Globalization;

namespace GtaAnything.Runtime.Compatibility
{
    /// <summary>
    /// Identifies the target GTA V generation and asset pipeline.
    /// </summary>
    public enum GameEdition
    {
        Unknown = 0,
        LegacyGen8 = 1,
        EnhancedGen9 = 2
    }

    /// <summary>
    /// Identifies the active script loader chain.
    /// </summary>
    public enum LoaderKind
    {
        Unknown = 0,
        ShvdnV3 = 1,
        ShvdnEnhanced = 2,
        RagePluginHook = 3
    }

    /// <summary>
    /// Tracks both the disk executable build version (e.g. "1.0.1158.16") and the
    /// Script Hook V internal build enum alias (e.g. "VER_EN_1_0_1158_13"), along
    /// with Gen8/Gen9 asset and render-target compatibility invariants.
    /// </summary>
    public sealed class GameBuildInfo
    {
        private readonly GameEdition _edition;
        private readonly string _diskExecutableVersion;
        private readonly string _scriptHookBuildAlias;
        private readonly string _executableName;

        public GameEdition Edition { get { return _edition; } }
        public string DiskExecutableVersion { get { return _diskExecutableVersion; } }
        public string ScriptHookBuildAlias { get { return _scriptHookBuildAlias; } }
        public string ExecutableName { get { return _executableName; } }

        /// <summary>
        /// True on GTA V Enhanced (Gen9), where script_rt_* dial/dashboard textures must use
        /// single-mip uncompressed B8G8R8A8_UNORM instead of legacy DXT1 to prevent crashes.
        /// </summary>
        public bool RequiresUncompressedScriptRenderTargets
        {
            get { return _edition == GameEdition.EnhancedGen9; }
        }

        /// <summary>
        /// Expected RSC vehicle fragment (.yft) version (171 for Gen9 Enhanced, 162 for Gen8 Legacy).
        /// </summary>
        public int ExpectedYftVersion
        {
            get { return _edition == GameEdition.EnhancedGen9 ? 171 : 162; }
        }

        /// <summary>
        /// Expected RSC texture dictionary (.ytd) version (5 for Gen9 Enhanced, 13 for Gen8 Legacy).
        /// </summary>
        public int ExpectedYtdVersion
        {
            get { return _edition == GameEdition.EnhancedGen9 ? 5 : 13; }
        }

        public GameBuildInfo(
            GameEdition edition,
            string diskExecutableVersion,
            string scriptHookBuildAlias,
            string executableName = null)
        {
            _edition = edition;
            _diskExecutableVersion = string.IsNullOrWhiteSpace(diskExecutableVersion)
                ? "0.0.0.0"
                : diskExecutableVersion.Trim();
            _scriptHookBuildAlias = string.IsNullOrWhiteSpace(scriptHookBuildAlias)
                ? "UNKNOWN_SHV_BUILD"
                : scriptHookBuildAlias.Trim();
            _executableName = !string.IsNullOrWhiteSpace(executableName)
                ? executableName.Trim()
                : (edition == GameEdition.EnhancedGen9 ? "GTA5_Enhanced.exe" : "GTA5.exe");
        }

        public override string ToString()
        {
            return string.Format(
                CultureInfo.InvariantCulture,
                "{0} [Exe={1}@{2}, SHV={3}, YFT=v{4}, YTD=v{5}, UncompressedScriptRT={6}]",
                Edition,
                ExecutableName,
                DiskExecutableVersion,
                ScriptHookBuildAlias,
                ExpectedYftVersion,
                ExpectedYtdVersion,
                RequiresUncompressedScriptRenderTargets);
        }
    }

    /// <summary>
    /// Detects the active GTA V edition and dual build identifiers from runtime telemetry
    /// or compile-time conditional symbols (GTAV_ENHANCED / GTAV_LEGACY).
    /// </summary>
    public static class GameEditionDetector
    {
        /// <summary>
        /// Returns the compile-time edition configured via GTAV_ENHANCED or GTAV_LEGACY symbols.
        /// </summary>
        public static GameEdition GetCompileTimeEdition()
        {
#if GTAV_ENHANCED
            return GameEdition.EnhancedGen9;
#elif GTAV_LEGACY
            return GameEdition.LegacyGen8;
#else
            return GameEdition.Unknown;
#endif
        }

        /// <summary>
        /// Resolves a complete <see cref="GameBuildInfo"/> recording both the disk executable version
        /// and the Script Hook V build enum alias.
        /// </summary>
        public static GameBuildInfo DetectFromEnvironment(
            string diskExeVersion = null,
            string shvBuildAlias = null,
            GameEdition? overrideEdition = null)
        {
            GameEdition edition = overrideEdition.HasValue
                ? overrideEdition.Value
                : InferEdition(diskExeVersion, shvBuildAlias);
            if (edition == GameEdition.Unknown)
            {
                edition = GetCompileTimeEdition();
            }

            string resolvedExeVer = diskExeVersion;
            if (string.IsNullOrWhiteSpace(resolvedExeVer))
            {
                resolvedExeVer = edition == GameEdition.EnhancedGen9 ? "1.0.1158.16" : "1.0.3351.0";
            }

            string resolvedAlias = shvBuildAlias;
            if (string.IsNullOrWhiteSpace(resolvedAlias))
            {
                resolvedAlias = edition == GameEdition.EnhancedGen9
                    ? "VER_EN_1_0_1158_13"
                    : "VER_1_0_3351_0";
            }

            string exeName = edition == GameEdition.EnhancedGen9 ? "GTA5_Enhanced.exe" : "GTA5.exe";
            return new GameBuildInfo(edition, resolvedExeVer, resolvedAlias, exeName);
        }

        private static GameEdition InferEdition(string diskExeVersion, string shvBuildAlias)
        {
            if (!string.IsNullOrWhiteSpace(shvBuildAlias))
            {
                string upper = shvBuildAlias.Trim().ToUpperInvariant();
                if (upper.Contains("VER_EN_") || upper.Contains("ENHANCED") || upper.Contains("GEN9"))
                {
                    return GameEdition.EnhancedGen9;
                }
                if (upper.StartsWith("VER_1_0_", StringComparison.Ordinal))
                {
                    return GameEdition.LegacyGen8;
                }
            }

            if (!string.IsNullOrWhiteSpace(diskExeVersion))
            {
                string trimmed = diskExeVersion.Trim();
                if (trimmed.StartsWith("1.0.11", StringComparison.Ordinal) ||
                    trimmed.StartsWith("1.0.8", StringComparison.Ordinal))
                {
                    return GameEdition.EnhancedGen9;
                }
                if (trimmed.StartsWith("1.0.3", StringComparison.Ordinal) ||
                    trimmed.StartsWith("1.0.2", StringComparison.Ordinal))
                {
                    return GameEdition.LegacyGen8;
                }
            }

            return GameEdition.Unknown;
        }
    }
}
