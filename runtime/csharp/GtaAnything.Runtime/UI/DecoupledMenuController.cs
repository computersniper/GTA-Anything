using System;
using System.Collections.Generic;

namespace GtaAnything.Runtime.UI
{
    /// <summary>
    /// Permitted preview modes during menu navigation.
    /// Live 3D vehicle spawning during menu scroll is structurally prohibited (Invariant #4).
    /// </summary>
    public enum MenuPreviewMode
    {
        StaticMetadata = 0,
        StaticSprite = 1
    }

    /// <summary>
    /// Lightweight static descriptor displayed while scrolling routes or vehicles in the menu.
    /// Contains zero 3D world handles.
    /// </summary>
    public sealed class StaticMenuCard
    {
        public string ItemId { get; }
        public string Title { get; }
        public string Subtitle { get; }
        public string SpriteDict { get; }
        public string SpriteName { get; }
        public string VanillaFallbackModel { get; }
        public string PreferredAddonModel { get; }

        public StaticMenuCard(
            string itemId,
            string title,
            string subtitle,
            string vanillaFallbackModel,
            string preferredAddonModel = null,
            string spriteDict = "commonmenu",
            string spriteName = "gradient_bgd")
        {
            if (string.IsNullOrWhiteSpace(itemId))
            {
                throw new ArgumentException("ItemId cannot be empty.", nameof(itemId));
            }
            if (string.IsNullOrWhiteSpace(vanillaFallbackModel))
            {
                throw new ArgumentException("VanillaFallbackModel cannot be empty.", nameof(vanillaFallbackModel));
            }

            ItemId = itemId.Trim();
            Title = title ?? ItemId;
            Subtitle = subtitle ?? string.Empty;
            VanillaFallbackModel = vanillaFallbackModel.Trim();
            PreferredAddonModel = string.IsNullOrWhiteSpace(preferredAddonModel) ? null : preferredAddonModel.Trim();
            SpriteDict = string.IsNullOrWhiteSpace(spriteDict) ? "commonmenu" : spriteDict.Trim();
            SpriteName = string.IsNullOrWhiteSpace(spriteName) ? "gradient_bgd" : spriteName.Trim();
        }
    }

    /// <summary>
    /// Enforces UI-Spawn Decoupling (Hard Engineering Invariant #4):
    /// Scrolling through menu items (<see cref="OnIndexChanged"/>) ONLY updates the active
    /// <see cref="StaticMenuCard"/> metadata and 2D sprite reference.
    /// World model streaming and 3D vehicle spawning occur ONLY after <see cref="ConfirmSelection"/>
    /// transitions the state machine into <c>ResourceStreaming</c>.
    /// </summary>
    public sealed class DecoupledMenuController
    {
        private readonly List<StaticMenuCard> _cards = new List<StaticMenuCard>();

        public string Title { get; }
        public string Subtitle { get; }
        public MenuPreviewMode PreviewMode { get; }
        public bool IsOpen { get; private set; }
        public int SelectedIndex { get; private set; }

        public IReadOnlyList<StaticMenuCard> Cards => _cards;

        public StaticMenuCard CurrentCard =>
            _cards.Count > 0 && SelectedIndex >= 0 && SelectedIndex < _cards.Count
                ? _cards[SelectedIndex]
                : null;

        public event Action<StaticMenuCard> OnCardHighlighted;
        public event Action<StaticMenuCard> OnCardConfirmed;

        public DecoupledMenuController(
            string title,
            string subtitle,
            MenuPreviewMode previewMode = MenuPreviewMode.StaticSprite)
        {
            Title = string.IsNullOrWhiteSpace(title) ? "GTA-Anything Dispatch" : title.Trim();
            Subtitle = subtitle ?? string.Empty;
            PreviewMode = previewMode;
        }

        /// <summary>
        /// Parses a Gameplay IR preview_mode string ("static_metadata" | "static_sprite") and rejects "live_3d_spawn".
        /// </summary>
        public static MenuPreviewMode ParsePreviewMode(string previewMode)
        {
            if (string.Equals(previewMode, "live_3d_spawn", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "Hard Invariant Violation: preview_mode 'live_3d_spawn' is prohibited in DecoupledMenuController.");
            }

            if (string.Equals(previewMode, "static_metadata", StringComparison.OrdinalIgnoreCase))
            {
                return MenuPreviewMode.StaticMetadata;
            }

            return MenuPreviewMode.StaticSprite;
        }

        public void AddCard(StaticMenuCard card)
        {
            if (card == null)
            {
                throw new ArgumentNullException(nameof(card));
            }
            _cards.Add(card);
        }

        public void Open()
        {
            IsOpen = true;
            if (_cards.Count > 0 && SelectedIndex >= _cards.Count)
            {
                SelectedIndex = 0;
            }
        }

        public void Close()
        {
            IsOpen = false;
        }

        /// <summary>
        /// Handles menu scroll changes purely in memory (zero 3D entity allocation).
        /// </summary>
        public StaticMenuCard OnIndexChanged(int newIndex)
        {
            if (_cards.Count == 0)
            {
                SelectedIndex = 0;
                return null;
            }

            int normalized = newIndex % _cards.Count;
            if (normalized < 0)
            {
                normalized += _cards.Count;
            }

            SelectedIndex = normalized;
            StaticMenuCard current = CurrentCard;
            OnCardHighlighted?.Invoke(current);
            return current;
        }

        /// <summary>
        /// Closes the selection menu and returns the confirmed <see cref="StaticMenuCard"/>
        /// so the caller can transition into <c>ResourceStreaming</c>.
        /// </summary>
        public StaticMenuCard ConfirmSelection()
        {
            StaticMenuCard confirmed = CurrentCard;
            IsOpen = false;
            if (confirmed != null)
            {
                OnCardConfirmed?.Invoke(confirmed);
            }
            return confirmed;
        }
    }
}
