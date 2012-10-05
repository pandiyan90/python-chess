import libchess
import re

class Position(object):
    """Represents a chess position."""

    def __init__(self):
        """Inits an empty position."""
        self._board = [None] * 128
        self._turn = "w"
        self._castling = ""
        self._ep_file = None
        self._half_moves = 0
        self._move_number = 1

    def copy(self):
        """Gets a copy of the position. The copy will not change when the
        original instance is changed.

        Returns:
            An exact copy of the positon.
        """
        return Position.from_fen(self.get_fen())

    def get(self, square):
        """Gets the piece on the given square.

        Args:
            square: A Square object.

        Returns:
            A piece object for the piece that is on that square or None if
            there is no piece on the square.
        """
        return self._board[square.get_0x88_index()]

    def set(self, square, piece):
        """Sets a piece on the given square.

        Args:
            square: The square to set the piece on.
            piece: The piece to set. None to clear the square.
        """
        self._board[square.get_0x88_index()] = piece

        # Update castling rights.
        for type in ["K", "Q", "k", "q"]:
            if not self.get_theoretical_castling_right(type):
                self.set_castling_right(type, False)

    def clear(self):
        """Removes all pieces from the board."""
        self._board = [None] * 128
        self._castling = ""

    def reset(self):
        """Resets to the default chess position."""
        self.set_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1")

    def _get_disambiguator(self, move):
        """Gets a disambiguator used by SANs to make moves unambigous.

        Returns:
            A disambiguator to insert.
        """
        same_rank = False
        same_file = False
        piece = self.get(move.get_source())

        for m in self.get_legal_moves():
            ambig_piece = self.get(m.get_source())
            if piece == ambig_piece and move.get_source() != m.get_source() and move.get_target() == m.get_target():
                if move.get_source().get_rank() == m.get_source().get_rank():
                    same_rank = True

                if move.get_source().get_file() == m.get_source().get_file():
                    same_file = True

                if same_rank and same_file:
                    break

        if same_rank and same_file:
            return move.get_source().get_name()
        elif same_file:
            return str(move.get_source().get_rank())
        elif same_rank:
            return move.get_source().get_file()
        else:
            return ""

    def get_move_info(self, move):
        """Gets information about a move.

        Args:
            move: The move to get information about.
        """
        assert move in self.get_legal_moves()
        resulting_position = self.copy()
        resulting_position.make_move(move)

        capture = self.get(move.get_target())
        piece = self.get(move.get_source())

        # Pawn moves.
        enpassant = False
        if piece.get_type() == "p":
            # En-passant.
            if move.get_target().get_file() != move.get_source().get_file() and not capture:
                enpassant = True
                capture = libchess.Piece(resulting_position.get_turn(), 'p')

        # Castling.
        is_king_side_castle = piece.get_type() == 'k' and move.get_target().get_x() - move.get_source().get_x() == 2
        is_queen_side_castle = piece.get_type() == 'k' and move.get_target().get_x() - move.get_source().get_x() == -2

        # Checks.
        is_check = resulting_position.is_check()
        is_checkmate = resulting_position.is_checkmate()

        # Generate the SAN.
        san = ""
        if is_king_side_castle:
            san += "o-o"
        elif is_queen_side_castle:
            san += "o-o-o"
        else:
            if piece.get_type() != 'p':
                san += piece.get_type().upper()

            san += self._get_disambiguator(move)

            if capture:
                if piece.get_type() == 'p':
                    san += move.get_source().get_file()
                san += "x"
            san += move.get_target().get_name()

            if move.get_promotion():
                san += "="
                san += move.get_promotion().upper()

        if is_checkmate:
            san += "#"
        elif is_check:
            san += "+"

        if enpassant:
            san += " (e.p.)"

        return libchess.MoveInfo(
            move=move,
            piece=piece,
            captured=capture,
            san=san,
            is_enpassant=enpassant,
            is_king_side_castle=is_king_side_castle,
            is_queen_side_castle=is_queen_side_castle,
            is_check=is_check,
            is_checkmate=is_checkmate)

    def make_move(self, move):
        """Makes a move.

        Args:
            move: The move to make.
        """
        capture = self.get(move.get_target())

        # Move the piece.
        self.set(move.get_target(), self.get(move.get_source()))
        self.set(move.get_source(), None)

        # It is the next players turn.
        self.toggle_turn()

        # Pawn moves.
        if self.get(move.get_target()).get_type() == 'p':
            # En-passant.
            if move.get_target().get_file() != move.get_source().get_file() and not capture:
                if self.get_turn() == "b":
                    self._board[move.get_target().get_0x88_index() - 16] = None
                else:
                    self._board[move.get_target().get_0x88_index() + 16] = None
                capture = True
            # If big pawn move, set the en-passant file.
            if abs(move.get_target().get_rank() - move.get_source().get_rank()) == 2:
                self._ep_file = move.get_target().get_file()
            else:
                self._ep_file = None
        else:
            self._ep_file = None

        # Promotion.
        if move.get_promotion():
            self.set(move.get_target(), libchess.Piece(self.get(move.get_target()).get_color(), move.get_promotion()))

        # Potential castling.
        if self.get(move.get_target()).get_type() == 'k':
            steps = move.get_target().get_x() - move.get_source().get_x()
            if abs(steps) == 2:
                # Queen-side castling.
                if steps == -2:
                    rook_target = move.get_target().get_0x88_index() + 1
                    rook_source = move.get_target().get_0x88_index() - 2
                # King-side castling.
                else:
                    rook_target = move.get_target().get_0x88_index() - 1
                    rook_source = move.get_target().get_0x88_index() + 1
                self._board[rook_target] = self._board[rook_source]
                self._board[rook_source] = None

        # Increment the half move counter.
        if self.get(move.get_target()).get_type() == 'p':
            self._half_moves = 0
        elif capture:
            self._half_moves = 0
        else:
            self._half_moves += 1

        # Increment the move number.
        if self.get_turn() == "w":
            self._move_number += 1


    def get_turn(self):
        """Gets whos turn it is.

        Returns:
            "w" if it is white's turn. "b" if it is black's turn.
        """
        return self._turn

    def set_turn(self, turn):
        """Sets whos turn it is.

        Args:
            turn: "w" if it is white's turn. "b" is it is black's turn.
        """
        assert turn in ["w", "b"]
        self._turn = turn

    def toggle_turn(self):
        """Toggles whos turn it is."""
        self.set_turn(libchess.opposite_color(self._turn))

    def get_castling_right(self, type):
        """Checks the castling rights.

        Args:
            type: The castling move to check for. "K" for kingside castling of
                white player, "Q" for queenside castling of the white player.
                "k" and "q" for the corresponding castling moves of the black
                 player.

        Returns:
            A boolean indicating whether the player has that castling right.
        """
        assert type in ["K", "Q", "k", "q"]
        return type in self._castling

    def get_theoretical_castling_right(self, type):
        """Checks if a player could have a castling right in theory from
        looking just at the piece positions.

        Args:
            type: The castling move to check for. "K", "Q", "k" or "q" as used
                by get_castling_right().

        Returns:
            A boolean indicating whether the player could theoretically have
            that castling right.
        """
        assert type in ["K", "Q", "k", "q"]
        if type == "K" or type == "Q":
            if self.get(libchess.Square.from_name('e1')) != libchess.Piece('w', 'k'):
                return False
            if type == "K":
                return self.get(libchess.Square.from_name('h1')) == libchess.Piece('w', 'r')
            elif type == "Q":
                return self.get(libchess.Square.from_name('a1')) == libchess.Piece('w', 'r')
        elif type == "k" or type == "q":
            if self.get(libchess.Square.from_name('e8')) != libchess.Piece('b', 'k'):
                return False
            if type == "k":
                return self.get(libchess.Square.from_name('h8')) == libchess.Piece('b', 'r')
            elif type == "q":
                return self.get(libchess.Square.from_name('a8')) == libchess.Piece('b', 'r')

    def set_castling_right(self, type, status):
        """Sets a castling right.

        Args:
            type: "K", "Q", "k" or "q" as used by get_castling_right() for the
                castling move types.
            status: A boolean indicating whether that castling right should be
                given or denied.
        """
        assert type in ["K", "Q", "k", "q"]
        assert not status or self.get_theoretical_castling_right(type)

        castling = ""
        for t in ["K", "Q", "k", "q"]:
            if type == t:
                if status:
                    castling += t
            elif self.get_castling_right(t):
                castling += t
        self._castling = castling

    def get_ep_file(self):
        """The en-passant file.

        Returns:
            The file on which a pawn has just moved two steps forward as "a",
            "b", "c", "d", "e", "f", "g", "h" or None, if there is no such
            file.
        """
        return self._ep_file

    def set_ep_file(self, file):
        """Sets the en-passant file.

        Args:
            file: The file on which a pawn has just moved two steps forward as
                "a", "b", "c", "d", "e", "f", "g", "h" or None, if there is no
                such file.
        """
        assert file in ["a", "b", "c", "d", "e", "f", "g", "h", None]
        self._ep_file = file

    def get_half_moves(self):
        """Gets the number of half-moves since the last capture or pawn move.

        Returns:
            An integer.
        """
        return self._half_moves

    def set_half_moves(self, half_moves):
        """Sets the number of half-moves since the last capture or pawn move.

        Args:
            half_moves: An integer.
        """
        half_moves = int(half_moves)
        assert half_moves >= 0
        self._half_moves = half_moves

    def get_move_number(self):
        """Gets the number of this move. The game starts at 1 and the counter
        is incremented every time white moves.

        Returns:
            An integer.
        """
        return self._move_number

    def set_move_number(self, move_number):
        """Sets the move number.

        Args:
            move_number: An integer.
        """
        return self._move_number

    def get_piece_counts(self, color = "wb"):
        """Gets a dictionary keyed by "p", "b", "n", "r", "k" and "q" with the
        counts of pawns, bishops, knights, rooks, kings and queens on the
        board.

        Args:
            color: A color to filter the pieces by. Defaults to "wb" for both
                black and white pieces. Valid arguments are "w", "b", "wb" and
                "bw".

        Returns:
            A dictionary of piece counts.
        """
        assert color in ["w", "b", "wb", "bw"]
        counts = {
            "p": 0,
            "b": 0,
            "n": 0,
            "r": 0,
            "k": 0,
            "q": 0,
        }
        for piece in self._board:
            if piece and piece.get_color() in color:
                counts[piece.get_type()] += 1
        return counts

    def get_king(self, color):
        """Gets the square of the king.

        Args:
            color: "w" for the white players king. "b" for the black players
                king.

        Returns:
            The square of the king or None if that player has no king.
        """
        assert color in ["w", "b"]
        for square in libchess.Square.get_all():
            piece = self.get(square)
            if piece and piece.get_color() == color and piece.get_type() == 'k':
                return square

    def get_fen(self):
        """Gets the FEN representation of the position.

        Returns:
            The fen string representing the position.
        """
        # Board setup.
        empty = 0
        fen = ""
        for y in range(7, -1, -1):
            for x in range(0, 8):
                i = libchess.Square(x, y).get_0x88_index()
                # Add pieces.
                if not self._board[i]:
                    empty += 1
                else:
                    if empty > 0:
                        fen += str(empty)
                        empty = 0
                    fen += self._board[i].get_symbol()

            # Border of the board.
            if empty > 0:
                fen += str(empty)
            if not (x == 7 and y == 0):
                fen += "/"
            empty = 0

        # Castling.
        castling_flag = "-"
        if self._castling:
            castling_flag = self._castling

        # En-passant.
        ep_flag = "-"
        if self._ep_file:
            ep_flag = self._ep_file
            if self._turn == "w":
                ep_flag += "6"
            else:
                ep_flag += "3"

        return " ".join([fen, self._turn, castling_flag, ep_flag, str(self._half_moves), str(self._move_number)])

    def set_fen(self, fen):
        """Sets the position by a FEN.

        Args:
            fen: The FEN.
        """
        # Split into 6 parts.
        tokens = fen.split()
        assert len(tokens) == 6

        # Check that every row is valid.
        rows = tokens[0].split("/")
        assert len(rows) == 8
        for row in rows:
            field_sum = 0
            previous_was_number = False
            for char in row:
                assert char in "12345678pnbrkqPNBRKQ"
                if char in "12345678":
                    assert not previous_was_number
                    field_sum += int(char)
                    previous_was_number = True
                else:
                    field_sum += 1
                    previous_was_number = False
            assert field_sum == 8

        # Assertions.
        assert tokens[1] in ["w", "b"]
        assert re.compile("^(KQ?k?q?|Qk?q?|kq?|q|-)$").match(tokens[2])
        assert re.compile("^(-|[a-h][36])$").match(tokens[3])

        # Set the move counters.
        half_moves = int(tokens[4])
        assert half_moves >= 0
        move_number = int(tokens[5])
        assert move_number >= 1
        self._half_moves = half_moves
        self._move_number = move_number

        # Set the en-passant file.
        if tokens[3] == "-":
            self._ep_file = None
        else:
            self._ep_file = tokens[3][0]

        # Set the castling.
        if tokens[2] == "-":
            self._castling = ""
        else:
            self._castling = tokens[2]

        # Set pieces on the board.
        self._board = [None] * 128
        i = 0
        for symbol in tokens[0]:
            if symbol == "/":
                i += 8
            elif symbol in "12345678":
                i += int(symbol)
            else:
                self._board[i] = libchess.Piece.from_symbol(symbol)
                i += 1

        # Set the turn.
        self._turn = tokens[1]

        # Update castling rights.
        for type in ["K", "Q", "k", "q"]:
            if not self.get_theoretical_castling_right(type):
               self.set_castling_right(type, False)

    def validate():
        """Validates the position. Castling rights are automatically corrected,
        invalid en-passant flags are ignored. Players can have more attackers
        on their king than is possible through discovery.

        Methods that require legal move generation and material counting assume
        the position is valid. If not, their results are undefined.

        Raises:
            - Missing black king.
            - Missing white king.
            - Too many black kings.
            - Too many white kings.
            - Too many black pawns.
            - Too many white pawns.
            - Too many black pieces.
            - Too many white pieces.
            - Both sides in check.
            - Opposite king in check.
        """
        for color in ["white", "black"]:
            piece_counts = self.get_piece_counts(color[0])
            if piece_counts["k"] == 0:
                raise "Missing %s king." % color
            elif piece_counts["k"] > 1:
                raise "Too many %s kings." % color

            if piece_counts["p"] > 8:
                raise "Too many %s pawns." % color

            if sum(piece_counts.values()) > 16:
                raise "Too many %s pieces." % color

        if self.is_king_attacked("w") and self.is_king_attacked("b"):
            raise "Both sides in check."

        if self.is_king_attacked(libchess.opposite_color(self.get_turn())):
            raise "Opposite king in check."

    def is_king_attacked(self, color):
        """Checks if the king of a player is attacked.

        color: Check if the king of this color is attacked.

        Returns:
            A boolean indicating whether the king is attacked.
        """
        square = self.get_king(color)
        if square:
            return self.is_attacked(libchess.opposite_color(color), square)
        else:
            return False

    def get_pseudo_legal_moves(self):
        """Gets pseudo legal moves in the current position.

        Yields: Pseudo legal moves.
        """
        PAWN_OFFSETS = {
            "b": [16, 32, 16, 15],
            "w": [-16, -32, -17, -15]
        }

        PIECE_OFFSETS = {
            "n": [-18, -33, -31, -14, 18, 33, 31, 14],
            "b": [-17, -15, 17, 15],
            "r": [-16, 1, 16, -1],
            "q": [-17, -16, -15, 1, 17, 16, 15, -1],
            "k": [-17, -16, -15, 1, 17, 16, 15, -1]
        }

        for square in libchess.Square.get_all():
            # Skip pieces of the opponent.
            piece = self.get(square)
            if not piece or piece.get_color() != self.get_turn():
                continue

            # Pawn moves.
            if piece.get_type() == "p":
                # Single square ahead. Do not capture.
                target = libchess.Square.from_0x88_index(square.get_0x88_index() + PAWN_OFFSETS[self.get_turn()][0])
                if not self.get(target):
                    # Promotion.
                    if target.is_backrank():
                        for promote_to in "bnrq":
                            yield libchess.Move(square, target, promote_to)

                    # Two squares ahead. Do not capture.
                    target = libchess.Square.from_0x88_index(square.get_0x88_index() + PAWN_OFFSETS[self.get_turn()][1])
                    if (self.get_turn() == "w" and square.get_rank() == 2) or (self.get_turn() == "b" and square.get_rank() == 7) and not self.get(target):
                        yield libchess.Move(square, target)

                # Pawn captures.
                for j in [2, 3]:
                   target_index = square.get_0x88_index() + PAWN_OFFSETS[self.get_turn()][j]
                   if target_index & 0x88:
                       continue
                   target = libchess.Square.from_0x88_index(target_index)
                   if self.get(target) and self.get(target).get_color() != self.get_turn():
                       # Promotion.
                       if target.is_backrank():
                           for promote_to in "bnrq":
                               yield libchess.Move(square, target, promote_to)
                       else:
                           yield libchess.Move(square, target)
                   # En-passant.
                   elif not self.get(target) and target.get_file() == self._ep_file:
                       yield libchess.Move(square, target)
            # Other pieces.
            else:
                for offset in PIECE_OFFSETS[piece.get_type()]:
                    target_index = square.get_0x88_index()
                    while True:
                        target_index += offset
                        if target_index & 0x88:
                            break
                        target = libchess.Square.from_0x88_index(target_index)
                        if not self.get(target):
                            yield libchess.Move(square, target)
                        else:
                            if self.get(target).get_color() == self.get_turn():
                                break
                            yield libchess.Move(square, target)
                            break

                        # Knight and king do not go multiple times in their
                        # direction.
                        if piece.get_type() in ["n", "k"]:
                            break

        opponent = libchess.opposite_color(self.get_turn())

        # King-side castling.
        k = "k" if self.get_turn() == "b" else "K"
        if self.get_castling_right(k):
            of = self.get_king(self.get_turn()).get_0x88_index()
            to = of + 2
            if not self._board[of + 1] and not self._board[to] and not self.is_check() and not self.is_attacked(opponent, libchess.Square.from_0x88_index(of + 1)) and not self.is_attacked(opponent, libchess.Square.from_0x88_index(to)):
                yield libchess.Move(libchess.Square.from_0x88_index(of), libchess.Square.from_0x88_index(to))

        # Queen-side castling
        q = "q" if self.get_turn() == "b" else "Q"
        if self.get_castling_right(q):
            of = self.get_king(self.get_turn()).get_0x88_index()
            to = of - 2

            if not self._board[of - 1] and not self._board[of - 2] and not self._board[of - 3] and not self.is_check() and not self.is_attacked(opponent, libchess.Square.from_0x88_index(of - 1)) and not self.is_attacked(opponent, libchess.Square.from_0x88_index(to)):
                yield libchess.Move(libchess.Square.from_0x88_index(of), libchess.Square.from_0x88_index(to))

    def get_legal_moves(self):
        """Gets legal moves in the current position.

        Yields: All legal moves.
        """
        for move in self.get_pseudo_legal_moves():
            potential_position = self.copy()
            potential_position.make_move(move)
            if not potential_position.is_king_attacked(self.get_turn()):
                yield move

    def get_attackers(self, color, square):
        """Gets the attackers of a specific square.

        Args:
            color: Filter by this color.
            square: The square to check for.

        Yields:
            Source squares of the attack.
        """
        assert color in ["b", "w"]

        ATTACKS = [
            20, 0, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 0, 20, 0,
            0, 20, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 20, 0, 0,
            0, 0, 20, 0, 0, 0, 0, 24, 0, 0, 0, 0, 20, 0, 0, 0,
            0, 0, 0, 20, 0, 0, 0, 24, 0, 0, 0, 20, 0, 0, 0, 0,
            0, 0, 0, 0, 20, 0, 0, 24, 0, 0, 20, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 20, 2, 24, 2, 20, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 2, 53, 56, 53, 2, 0, 0, 0, 0, 0, 0,
            24, 24, 24, 24, 24, 24, 56, 0, 56, 24, 24, 24, 24, 24, 24, 0,
            0, 0, 0, 0, 0, 2, 53, 56, 53, 2, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 20, 2, 24, 2, 20, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 20, 0, 0, 24, 0, 0, 20, 0, 0, 0, 0, 0,
            0, 0, 0, 20, 0, 0, 0, 24, 0, 0, 0, 20, 0, 0, 0, 0,
            0, 0, 20, 0, 0, 0, 0, 24, 0, 0, 0, 0, 20, 0, 0, 0,
            0, 20, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 20, 0, 0,
            20, 0, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 0, 20
        ]

        RAYS = [
            17, 0, 0, 0, 0, 0, 0, 16, 0, 0, 0, 0, 0, 0, 15, 0,
            0, 17, 0, 0, 0, 0, 0, 16, 0, 0, 0, 0, 0, 15, 0, 0,
            0, 0, 17, 0, 0, 0, 0, 16, 0, 0, 0, 0, 15, 0, 0, 0,
            0, 0, 0, 17, 0, 0, 0, 16, 0, 0, 0, 15, 0, 0, 0, 0,
            0, 0, 0, 0, 17, 0, 0, 16, 0, 0, 15, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 17, 0, 16, 0, 15, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 17, 16, 15, 0, 0, 0, 0, 0, 0, 0,
            1, 1, 1, 1, 1, 1, 1, 0, -1, -1, -1, -1, -1, -1, -1, 0,
            0, 0, 0, 0, 0, 0, -15, -16, -17, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, -15, 0, -16, 0, -17, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, -15, 0, 0, -16, 0, 0, -17, 0, 0, 0, 0, 0,
            0, 0, 0, -15, 0, 0, 0, -16, 0, 0, 0, -17, 0, 0, 0, 0,
            0, 0, -15, 0, 0, 0, 0, -16, 0, 0, 0, 0, -17, 0, 0, 0,
            0, -15, 0, 0, 0, 0, 0, -16, 0, 0, 0, 0, 0, -17, 0, 0,
            -15, 0, 0, 0, 0, 0, 0, -16, 0, 0, 0, 0, 0, 0, -17
        ]

        SHIFTS = {
            "p": 0,
            "n": 1,
            "b": 2,
            "r": 3,
            "q": 4,
            "k": 5
        }

        for source in libchess.Square.get_all():
            piece = self.get(source)
            if not piece or piece.get_color() != color:
                continue

            difference = source.get_0x88_index() - square.get_0x88_index()
            index = difference + 119

            if ATTACKS[index] & (1 << SHIFTS[piece.get_type()]):
                # Handle pawns.
                if piece.get_type() == "p":
                    if difference > 0:
                        if piece.get_color() == "w":
                            yield source
                    else:
                        if piece.get_color() == "b":
                            yield source
                    continue

                # Handle knights and king.
                if piece.get_type() in ["n", "k"]:
                    yield source

                # Handle the others.
                offset = RAYS[index]
                j = source.get_0x88_index() + offset
                blocked = False
                while j != square.get_0x88_index():
                    if self._board[j]:
                        blocked = True
                        break
                    j += offset
                if not blocked:
                    yield source

    def is_attacked(self, color, square):
        """Checks whether a square is attacked.

        Args:
            color: Check if this player is attacking.
            square: The square he might be attacking.

        Returns:
            A boolean indicating whether the given square is attacked by the
            player of the given color.
        """
        try:
            self.get_attackers(color, square).next()
            return True
        except StopIteration:
            return False

    def is_check(self):
        """Checks for checks.

        Returns:
            A boolean indicating whether the current player is in check.
        """
        return self.is_king_attacked(self.get_turn())

    def is_checkmate(self):
        """Checks for checkmates.

        Returns:
            A boolean indicating whether the current player has been
            checkmated.
        """
        if not self.is_check():
            return False
        else:
            try:
                self.get_legal_moves().next()
                return False
            except StopIteration:
                return True

    def is_stalemate(self):
        """Checks for stalemates.

        Returns:
            A boolean indicating whether the current player is in stalemate.
        """
        if self.is_check():
            return False
        else:
            try:
                self.get_legal_moves().next()
                return False
            except StopIteration:
                return True

    def is_insufficient_material(self):
        """Checks if thee is sufficient material to mate.

        Mating is impossible in:
        - A king versus king endgame.
        - A king with bishop versus king endgame.
        - A king with knight versus king endgame.
        - A king with bishop versus king with bishop endgame, where both
          bishops are on the same color. Same goes for additional bishops on
          the same color.

        Assumes that the position is valid and each player has exactly one
        king.

        Returns:
            A boolean indicating whether there is insufficient material to
            mate.
        """
        piece_counts = self.get_piece_counts()
        if sum(piece_counts.values()) == 2:
            # King versus king.
            return True
        elif sum(piece_counts.values()) == 3:
            # King and knight or bishop versus king.
            if piece_counts["b"] == 1 or piece_counts["n"] == 1:
                return True
        elif sum(piece_counts.values()) == 2 + piece_counts["b"]:
            # Each player with only king and any number of bishops, where all
            # bishops are on the same color.
            white_has_bishop = self.get_piece_counts("w")["b"] != 0
            black_has_bishop = self.get_piece_counts("b")["b"] != 0
            if white_has_bishop and black_has_bishop:
                color = None
                for square in libchess.Square.get_all():
                    if self.get(square) and self.get(square).get_type() == "b":
                        if color != None and color != square.is_light():
                            return False
                        color = square.is_light()
                return True
        return False

    def is_game_over(self):
        """Checks if the game is over by the rules of chess, disregarding that
        players can agree on a draw, claim a draw or resign.

        Returns:
            A boolean indicating whether the game is over.
        """
        return self.is_checkmate() or self.is_stalemate() or self.is_insufficient_material()

    def __str__(self):
        return self.get_fen()

    def __repr__(self):
        return "Position.from_fen('%s)" % self.get_fen()

    def __eq__(self, other):
        return self.get_fen() == other.get_fen()

    def __ne__(self, other):
        return self.get_fen() != other.get_fen()

    def __hash__(self, other):
        # TODO: Use Zobrist hashing.
        return hash(self.get_fen())

    @staticmethod
    def get_default():
        """Gets the default position.

        Returns:
            A new position, initialized to the default chess position.
        """
        default_position = Position()
        default_position.reset()
        return default_position

    @staticmethod
    def from_fen(fen):
        """Gets a position from a FEN.

        Args:
            fen: The FEN.

        Returns:
            A new position created from the fen.
        """
        position = Position()
        position.set_fen(fen)
        return position
