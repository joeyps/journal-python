/* An InfoBox is like an info window, but it displays
 * under the marker, opens quicker, and has flexible styling.
 * @param {GLatLng} latlng Point to place bar at
 * @param {Map} map The map on which to display this InfoBox.
 * @param {Object} opts Passes configuration options - content,
 *   offsetVertical, offsetHorizontal, className, height, width
 */
function InfoBox(opts) {
	google.maps.OverlayView.call(this);
	this.position_ = opts.position;
	this.map_ = opts.map;
	this.content_ = opts.content;
	this.height_ = 0;
	this.width_ = 0;
	this.offset_ = opts.pixelOffset;
	this.offsetHorizontal_ = 0;
	this.offsetVertical_ = 0;

	var me = this;

	// Once the properties of this OverlayView are initialized, set its map so
	// that we can display it.  This will trigger calls to panes_changed and
	// draw.
	if(this.map_ != undefined) {
		this.open(this.map_);
	}
}

/* InfoBox extends GOverlay class from the Google Maps API
 */
InfoBox.prototype = new google.maps.OverlayView();

/* Creates the DIV representing this InfoBox
 */
InfoBox.prototype.remove = function() {
	if (this.div_) {
		this.div_.parentNode.removeChild(this.div_);
		this.div_ = null;
	}
};

/* Redraw the Bar based on the current projection and zoom level
 */
InfoBox.prototype.draw = function() {
	// Creates the element if it doesn't exist already.
	this.createElement();
	if (!this.div_) return;

	// Calculate the DIV coordinates of two opposite corners of our bounds to
	// get the size and position of our Bar
	var pixPosition = this.getProjection().fromLatLngToDivPixel(this.position_);
	if (!pixPosition) return;

	// Now position our DIV based on the DIV coordinates of our bounds
	this.div_.style.width = this.width_ + "px";
	this.div_.style.left = (pixPosition.x + this.offsetHorizontal_) + "px";
	this.div_.style.height = this.height_ + "px";
	this.div_.style.top = (pixPosition.y + this.offsetVertical_) + "px";
	//this.div_.style.display = 'block';
	this.div_.style.visibility = "visible";
};

/* Creates the DIV representing this InfoBox in the floatPane.  If the panes
 * object, retrieved by calling getPanes, is null, remove the element from the
 * DOM.  If the div exists, but its parent is not the floatPane, move the div
 * to the new pane.
 * Called from within draw.  Alternatively, this can be called specifically on
 * a panes_changed event.
 */
InfoBox.prototype.createElement = function() {
	var panes = this.getPanes();
	var div = this.div_;
	if (!div) {
		// This does not handle changing panes.  You can set the map to be null and
		// then reset the map to move the div.
		div = this.div_ = document.createElement("div");
		div.style.backgroundColor = "#fff";
		div.style.position = "absolute";
		div.style.boxShadow = "5px 5px 6px rgba(0, 0, 0, 0.3)";
		//    div.style.width = this.width_ + "px";
		//    div.style.height = this.height_ + "px";

		var closeImg = document.createElement("img");
		closeImg.style.width = "32px";
		closeImg.style.height = "32px";
		closeImg.style.cursor = "pointer";
		closeImg.src = "/static/images/close.gif";
		closeImg.style.position = "absolute";
		closeImg.style.top = "5px";
		closeImg.style.right = "5px";

		function removeInfoBox(ib) {
				return function() {
				ib.setMap(null);
			};
		}

		google.maps.event.addDomListener(closeImg, 'click', removeInfoBox(this));

		if(this.content_) {
			var wrapper= document.createElement('div');
			wrapper.innerHTML = this.content_;
			div.appendChild(wrapper.firstChild);
		}
		div.appendChild(closeImg);
		//div.style.display = 'none';
		div.style.visibility = "hidden";
		panes.floatPane.appendChild(div);

		this.width_ = this.div_.clientWidth;
		this.height_ = this.div_.clientHeight;
		this.offsetHorizontal_ = (-this.width_/2) + (this.offset_? this.offset_.width : 0);
		this.offsetVertical_ = (-this.height_) + (this.offset_? this.offset_.height : 0);
		this.panMap();
	} else if (div.parentNode != panes.floatPane) {
		// The panes have changed.  Move the div.
		div.parentNode.removeChild(div);
		panes.floatPane.appendChild(div);
	} else {
		// The panes have not changed, so no need to create or move the div.
	}
}

/* Pan the map to fit the InfoBox.
 */
InfoBox.prototype.panMap = function() {
	// if we go beyond map, pan map
	var map = this.map_;
	var bounds = map.getBounds();
	var xOffset = 0, yOffset = 0;
	if (!bounds) return;

	if (!bounds.contains(this.position_)) {
		// Marker not in visible area of map, so set center
		// of map to the marker position first.
		map.setCenter(this.position_);
	}
	
	// The position of the infowindow
	var pixPosition = this.getProjection().fromLatLngToContainerPixel(this.position_);

	// The dimension of the infowindow
	var iwWidth = this.width_;
	var iwHeight = this.height_;

	// The offset position of the infowindow
	var iwOffsetX = this.offsetHorizontal_;
	var iwOffsetY = this.offsetVertical_;

	// Padding on the infowindow
	var padX = 40;
	var padY = 40;

	// The degrees per pixel
	var mapDiv = map.getDiv();
	var mapWidth = mapDiv.offsetWidth;
	var mapHeight = mapDiv.offsetHeight;

	if (pixPosition.x < (-iwOffsetX + padX)) {
		xOffset = pixPosition.x + iwOffsetX - padX;
	} else if ((pixPosition.x + iwWidth + iwOffsetX + padX) > mapWidth) {
		xOffset = pixPosition.x + iwWidth + iwOffsetX + padX - mapWidth;
	}
	if (this.alignBottom_) {
		if (pixPosition.y < (-iwOffsetY + padY + iwHeight)) {
			yOffset = pixPosition.y + iwOffsetY - padY - iwHeight;
		} else if ((pixPosition.y + iwOffsetY + padY) > mapHeight) {
			yOffset = pixPosition.y + iwOffsetY + padY - mapHeight;
		}
	} else {
		if (pixPosition.y < (-iwOffsetY + padY)) {
			yOffset = pixPosition.y + iwOffsetY - padY;
		} else if ((pixPosition.y + iwHeight + iwOffsetY + padY) > mapHeight) {
			yOffset = pixPosition.y + iwHeight + iwOffsetY + padY - mapHeight;
		}
	}

	if (!(xOffset === 0 && yOffset === 0)) {

	// Move the map to the shifted center.
	//
	var c = map.getCenter();
		map.panBy(xOffset, yOffset);
	}

	// Remove the listener after panning is complete.
	google.maps.event.removeListener(this.boundsChangedListener_);
	this.boundsChangedListener_ = null;
};

InfoBox.prototype.setContent = function(html) {
	this.content_ = html;
};

InfoBox.prototype.open = function(map, marker) {
	var me = this;
	if (marker)
		this.position_ = marker.getPosition();
	this.map_ = map;
	if(this.map_ && !this.boundsChangedListener_) {
		this.boundsChangedListener_ = google.maps.event.addListener(this.map_, "bounds_changed", function() {
			return me.panMap.apply(me);
		});
	}
	if(this.position_)
		this.setMap(this.map_);
};