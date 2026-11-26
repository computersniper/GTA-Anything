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
        private readonly string _itemId;
        private readonly string _title;
        private readonly string _subtitle;
        private readonly string _spriteDict;
        private readonly string _spriteName;
        private readonly string _vanillaFallbackModel;
        private readonly string _preferredAddonModel;

        public string ItemId { get { return _itemId; } }
        public string Title { get { return _title; } }
        public string Subtitle { get { return _subtitle; } }
        public string SpriteDict { get { return _spriteDict; } }
        public string SpriteName { get { return _spriteName; } }
        public string VanillaFallbackModel { get { return _vanillaFallbackModel; } }
        public string PreferredAddonModel { get { return _preferredAddonModel; } }

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
                throw new ArgumentException("ItemId cannot be empty.", "itemId");
            }
            if (string.IsNullOrWhiteSpace(vanillaFallbackModel))
            {
                throw new ArgumentException("VanillaFallbackModel cannot be empty.", "vanillaFallbackModel");
            }

            _itemId = itemId.Trim();
            _title = title ?? _itemId;
            _subtitle = subtitle ?? string.Empty;
            _vanillaFallbackModel = vanillaFallbackModel.Trim();
            _preferredAddonModel = string.IsNullOrWhiteSpace(preferredAddonModel) ? null : preferredAddonModel.Trim();
            _spriteDict = string.IsNullOrWhiteSpace(spriteDict) ? "commonmenu" : spriteDict.Trim();
            _spriteName = string.IsNullOrWhiteSpace(spriteName) ? "gradient_bgd" : spriteName.Trim();
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
        private readonly string _title;
        private readonly string _subtitle;
        private readonly MenuPreviewMode _previewMode;

        public string Title { get { return _title; } }
        public string Subtitle { get { return _subtitle; } }
        public MenuPreviewMode PreviewMode { get { return _previewMode; } }
        public bool IsOpen { get; private set; }
        public int SelectedIndex { get; private set; }

        public IReadOnlyList<StaticMenuCard> Cards { get { return _cards; } }

        public StaticMenuCard CurrentCard
        {
            get
            {
                return _cards.Count > 0 && SelectedIndex >= 0 && SelectedIndex < _cards.Count
                    ? _cards[SelectedIndex]
                    : null;
            }
        }

        public event Action<StaticMenuCard> OnCardHighlighted;
        public event Action<StaticMenuCard> OnCardConfirmed;

        public DecoupledMenuController(
            string title,
            string subtitle,
            MenuPreviewMode previewMode = MenuPreviewMode.StaticSprite)
        {
            _title = string.IsNullOrWhiteSpace(title) ? "GTA-Anything Dispatch" : title.Trim();
            _subtitle = subtitle ?? string.Empty;
            _previewMode = previewMode;
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
                throw new ArgumentNullException("card");
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
            Action<StaticMenuCard> handler = OnCardHighlighted;
            if (handler != null)
            {
                handler(current);
            }
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
                Action<StaticMenuCard> handler = OnCardConfirmed;
                if (handler != null)
                {
                    handler(confirmed);
                }
            }
            return confirmed;
        }
    }
}
