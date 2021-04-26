# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Liblarch - a library to handle directed acyclic graphs
# Copyright (c) 2011-2012 - Lionel Dricot & Izidor Matušov
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

from gi.repository import Gtk, GObject, GLib


class TreeModel(Gtk.TreeStore):
    """ Local copy of showed tree """

    def __init__(self, tree, types):
        """ Initializes parent and create list of columns. The first colum
        is node_id of node """

        self.count = 0
        self.count2 = 0

        self.types = [[str, lambda node: node.get_id()]] + types
        only_types = [python_type for python_type, access_method in self.types]

        super(TreeModel, self).__init__(*only_types)
        self.cache_paths = {}
        self.cache_position = {}
        self.tree = tree

    def set_column_function(self, column_num, column_func):
        """ Replace function for generating certain column.

        Original use case was changing method of generating background
        color during runtime - background by tags or due date """

        if column_num < len(self.types):
            self.types[column_num][1] = column_func
            return True
        else:
            return False

    def connect_model(self):
        """ Register "signals", callbacks from liblarch.

        Also asks for the current status by providing add_task callback.
        We are able to connect to liblarch tree on the fly. """

        self.tree.register_cllbck('node-added-inview', self.add_task)
        self.tree.register_cllbck('node-deleted-inview', self.remove_task)
        self.tree.register_cllbck('node-modified-inview', self.update_task)
        self.tree.register_cllbck('node-children-reordered', self.reorder_nodes)

        # Request the current state
        self.tree.get_current_state()

    def my_get_iter(self, path):
        """
        Because we sort the TreeStore, paths in the treestore are
        not the same as paths in the FilteredTree. We do the  conversion here.
        We receive a Liblarch path as argument and return a Gtk.TreeIter
        """
        # The function is recursive. We take iter for path (A, B, C) in cache.
        # If there is not, we take iter for path (A, B) and try to find C.
        if path == ():
            return None
        nid = str(path[-1])
        self.count += 1
        # We try to use the cache
        iter = self.cache_paths.get(path, None)
        toreturn = None
        if (iter and self.iter_is_valid(iter) and nid == self.get_value(iter, 0)):
            self.count2 += 1
            toreturn = iter
        else:
            root = self.my_get_iter(path[:-1])
            # This is a small ad-hoc optimisation.
            # Instead of going through all the children nodes
            # We go directly at the last known position.
            pos = self.cache_position.get(path, None)
            if pos:
                iter = self.iter_nth_child(root, pos)
                if iter and self.get_value(iter, 0) == nid:
                    toreturn = iter
            if not toreturn:
                if root:
                    iter = self.iter_children(root)
                else:
                    iter = self.get_iter_first()
                while iter and self.get_value(iter, 0) != nid:
                    iter = self.iter_next(iter)
            self.cache_paths[path] = iter
            toreturn = iter
        return toreturn

    def print_tree(self):
        """ Print TreeStore as Tree into console """

        def push_to_stack(stack, level, iterator):
            """ Macro which adds a new element into stack if it is possible """
            if iterator is not None:
                stack.append((level, iterator))

        stack = []
        push_to_stack(stack, 0, self.get_iter_first())

        print("+" * 50)
        print("Treemodel print_tree: ")
        while stack != []:
            level, iterator = stack.pop()

            print("=>" * level, self.get_value(iterator, 0))

            push_to_stack(stack, level, self.iter_next(iterator))
            push_to_stack(stack, level + 1, self.iter_children(iterator))
        print("+" * 50)

    # INTERFACE TO LIBLARCH ###################################################
    def add_task(self, node_id, path):
        """ Add new instance of node_id to position described at path.

        @param node_id: identification of task
        @param path: identification of position
        """
        node = self.tree.get_node(node_id)

        # Build a new row
        row = []
        for python_type, access_method in self.types:
            value = access_method(node)
            row.append(value)

        # Find position to add task
        iter_path = path[:-1]

        iterator = self.my_get_iter(iter_path)
        self.cache_position[path] = self.iter_n_children(iterator)
        self.insert(iterator, -1, row)

    def remove_task(self, node_id, path):
        """ Remove instance of node.

        @param node_id: identification of task
        @param path: identification of position
        """
        it = self.my_get_iter(path)
        if not it:
            raise Exception(
                "Trying to remove node %s with no iterator" % node_id)
        actual_node_id = self.get_value(it, 0)
        assert actual_node_id == node_id
        self.remove(it)
        self.cache_position.pop(path)

    def update_task(self, node_id, path):
        """ Update instance of node by rebuilding the row.

        @param node_id: identification of task
        @param path: identification of position
        """
        # We cannot assume that the node is in the tree because
        # update is asynchronus
        # Also, we should consider that missing an update is not critical
        # and ignoring the case where there is no iterator
        if self.tree.is_displayed(node_id):
            node = self.tree.get_node(node_id)
            # That call to my_get_iter is really slow!
            iterator = self.my_get_iter(path)

            if iterator:
                for column_num, (__, access_method) in enumerate(self.types):
                    value = access_method(node)
                    if value is not None:
                        self.set_value(iterator, column_num, value)

    def reorder_nodes(self, node_id, path, neworder):
        """ Reorder nodes.

        This is deprecated signal. In the past it was useful for reordering
        showed nodes of tree. It was possible to delete just the last
        element and therefore every element must be moved to the last position
        and then deleted.

        @param node_id: identification of root node
        @param path: identification of poistion of root node
        @param neworder: new order of children of root node
        """

        if path is not None:
            it = self.my_get_iter(path)
        else:
            it = None
        self.reorder(it, neworder)
        self.print_tree()


class TreeModel2(GObject.GObject, Gtk.TreeModel):
    def __init__(self, tree, types):
        """
        Initializes parent and create list of columns.
        The first colum is node_id of node
        """

        self.count = 0

        self.types = [(str, lambda node: node.get_id())] + types
        for type_ in self.types:
            if len(type_) < 2:
                raise ValueError(
                    "type %r (for an column) needs at least 2 elements: The type itself and the getter-method" % (type_,))
            if not isinstance(type_[0], type) and not isinstance(type_[0], GObject.GType):
                raise TypeError("type %r doesn't have a type" % (type_,))
            if not callable(type_[1]):
                raise TypeError("type %r doesn't have a getter method" % (type_,))

        self.cache_paths = {}
        self.cache_position = {}
        self.tree = tree
        self._treeiter_paths = []
        self._treeiter_map = {}
        self.stamp = 1

        super(GObject.GObject, self).__init__()

        self.tree.register_cllbck('node-added-inview', self._node_added)
        self.tree.register_cllbck('node-deleted-inview', self._node_deleted)
        self.tree.register_cllbck('node-modified-inview', self._node_modified)
        self.tree.register_cllbck('node-children-reordered', self._node_children_reordered)
    def connect_model(self):
        pass  # TODO: Remove this

    def _node_added(self, node_id, path):
        """
        Add new instance of node_id to position described at path.

        @param node_id: identification of task
        @param path: identification of position
        """
        self._invalidate_treeiters()
        iter, newpath = self._get_treeiter_and_treepath(node_id, path)
        self.row_inserted(newpath, iter)

    def _node_deleted(self, node_id, path):
        """
        Remove instance of node.

        @param node_id: identification of task
        @param path: identification of position
        """
        self._invalidate_treeiters()
        treepath = self._get_treepath(path)
        self.row_deleted(treepath)

    def _node_modified(self, node_id, path):
        """
        Update instance of node by rebuilding the row.

        @param node_id: identification of task
        @param path: identification of position
        """
        self._invalidate_treeiters()
        iter, newpath = self._get_treeiter_and_treepath(node_id, path)
        self.row_changed(newpath, iter)

    def _node_children_reordered(self, node_id, path, neworder):
        """
        Reorder nodes.

        This is deprecated signal. In the past it was useful for reordering
        showed nodes of tree. It was possible to delete just the last
        element and therefore every element must be moved to the last position
        and then deleted.

        @param node_id: identification of root node
        @param path: identification of poistion of root node
        @param neworder: new order of children of root node
        """
        pass  # TODO
        print("IGNORING CHILDREN REORDERED")

    def set_column_function(self, column_num: int, column_func):
        """
        Replace function for generating certain column.

        Original use case was changing method of generating background
        color during runtime - background by tags or due date.
        """

        if column_num < len(self.types):
            if not callable(column_func):
                raise TypeError("new column_func %r needs to be a function" % (column_func,))
            self.types[column_num][1] = column_func
            return True
        else:
            return False

    def _get_treeiter(self, node, path, node_id=None) -> Gtk.TreeIter:
        """
        Returns the iterator for a specific node with the specific path.
        """
        iter = Gtk.TreeIter()
        iter.stamp = self.stamp

        if not isinstance(path, tuple):
            path = tuple(path)  # Because it is immutable, easy to return

        try:
            index = self._treeiter_map[path]
        except (ValueError, KeyError):
            self._treeiter_paths.append(path)
            index = len(self._treeiter_paths) - 1
            self._treeiter_map[path] = index

        iter.user_data = index
        return iter

    def _get_treeiter_and_treepath(self, node_id, path) -> (Gtk.TreeIter, Gtk.TreePath):
        iter = self._get_treeiter(None, path, node_id=node_id)
        path = self.do_get_path(iter)
        return (iter, path)

    def _get_treepath(self, path) -> Gtk.TreePath:
        indices = []
        node = None
        for node_id in path:
            nodes = self.tree.node_all_children(node)
            index = nodes.index(node_id)
            indices.append(index)
            node = nodes[index]

        return Gtk.TreePath.new_from_indices(indices)

    def _get_invalid_treeiter(self) -> Gtk.TreeIter:
        """
        Returns an iterator that is considered invalid.
        It always has a stamp of 0, which internally is considered invalid.
        """
        # TODO: Move it to a (constant) property
        iter = Gtk.TreeIter()
        iter.stamp = 0
        return iter

    def _invalidate_treeiters(self):
        """
        Invalidates all existing Gtk.TreeIter.

        A Gtk.TreeIter stays valid as long the tree doesn't change
        (and no signals being fired). However, unfortunately, we can't
        implement our own memory managment "solution", and thus need to
        allocate some memory to store the data, that'll then live
        forever until one of the above happens.
        Thus, as a side effect, it cleans up memory.
        """
        # Make sure stamp is in valid int range because it is written to
        # the TreeIter
        imin, imax = (GLib.MININT, GLib.MAXINT)
        umax = imax + abs(imin)
        new_stamp = ((self.stamp + abs(imin) + 1) % umax) - abs(imin)
        if new_stamp == 0:
            new_stamp += 1
        self.stamp = new_stamp
        self._treeiter_paths.clear()
        self._treeiter_map.clear()

    def _get_path(self, iter: Gtk.TreeIter):
        """
        Returns the liblarch path for the iter
        """
        return self._treeiter_paths[iter.user_data]

    def _get_node_and_path(self, iter: Gtk.TreeIter):
        """
        Returns the node and the liblarch path to that node.
        """
        path = self._get_path(iter)
        node = self.tree.get_node(path[-1])
        return (node, path)

    def my_get_iter(self, path) -> Gtk.TreeIter:
        """
        Because we sort the TreeStore, paths in the treestore are
        not the same as paths in the FilteredTree. We do the  conversion here.
        We receive a Liblarch path as argument and return a Gtk.TreeIter
        """
        if path == ():
            return None
        return self._get_treeiter(None, path)

    # Gtk.TreeModel interface implementation

    def do_get_flags(self) -> Gtk.TreeModelFlags:
        return 0

    def do_get_n_columns(self):
        return len(self.types)

    def do_get_column_type(self, index: int) -> GObject.GType:
        col_type = self.types[index][0]
        if isinstance(col_type, GObject.GType):
            return col_type
        return col_type
        gtype_map = {
            str: GObject.TYPE_GSTRING,
        }
        return gtype_map.get(col_type, GObject.TYPE_PYOBJECT)
        return self.types[index][0]

    def do_get_iter(self, treepath: Gtk.TreePath):
        try:
            node_id = None  # root
            path = []
            for index in treepath.get_indices():
                node_id = self.tree.node_nth_child(node_id, index)
                path.append(node_id)

            iter = self._get_treeiter(None, path)
            return (True, iter)
        except ValueError as e:
            return (False, self._get_invalid_treeiter())

    def do_get_path(self, iter: Gtk.TreeIter) -> Gtk.TreePath:
        assert iter.stamp == self.stamp
        if iter.stamp != self.stamp:
            return (False, self._get_invalid_treeiter())

        path = self._get_path(iter)
        return self._get_treepath(path)

    def do_get_value(self, iter: Gtk.TreeIter, column: int) -> GObject.Value:
        path = self._get_path(iter)
        node = self.tree.get_node(path[-1])
        value = self.types[column][1](node)
        if value is None:
            return GObject.Value(GObject.TYPE_POINTER, value)
        return value

    def do_iter_next(self, iter: Gtk.TreeIter) -> bool:
        assert iter.stamp == self.stamp
        if iter.stamp != self.stamp:
            return (False, self._get_invalid_treeiter())

        path = self._get_path(iter)
        node_id = path[-1]
        if len(path) > 2:
            parent_id = path[-2]
        else:
            parent_id = self.tree.get_root().get_id()

        next = self.tree.node_next(node_id, parent_id)
        if next is None:
            return (False, self._get_invalid_treeiter)
        new_path = path[:-1] + (next.get_id(),)
        return (True, self._get_treeiter(next, new_path))

    def do_iter_previous(self, iter: Gtk.TreeIter) -> bool:
        assert iter.stamp == self.stamp
        if iter.stamp != self.stamp:
            return (False, self._get_invalid_treeiter())

        path = self._get_path(iter)
        node_id = path[-1]
        if len(path) > 2:
            parent = self.tree.get_node(path[-2])
        else:
            parent = self.tree.get_node(None)

        nodes = self.tree.node_all_children(parent)
        index = nodes.index(node_id)
        new_index = index - 1
        if new_index < 0:
            return (False, self._get_invalid_treeiter())

        previous_id = nodes[new_index]
        new_path = path[:-1] + (previous_id.get_id(),)
        return (True, self._get_treeiter(None, new_path))

    def do_iter_children(self, iter: Gtk.TreeIter) -> (bool, Gtk.TreeIter):
        if iter is None:
            return self.do_iter_first()
        try:
            path = self._get_path(iter)
            node_id = self.tree.node_nth_child(path[-1], 0)
            new_path = path + (node_id,)

            return (True, self._get_treeiter(None, new_path))
        except ValueError:
            return (False, self._get_invalid_treeiter())

    def do_iter_has_child(self, iter: Gtk.TreeIter) -> bool:
        assert iter.stamp == self.stamp
        if iter.stamp != self.stamp:
            return (False, self._get_invalid_treeiter())
        path = self._get_path(iter)
        node_id = path[-1]
        return self.tree.node_has_child(node_id)

    def do_iter_n_children(self, iter: Gtk.TreeIter) -> int:
        if iter is None:
            node_id = None
        else:
            assert iter.stamp == self.stamp
            if iter.stamp != self.stamp:
                return (False, self._get_invalid_treeiter())
            path = self._get_path(iter)
            node_id = path[-1]
        return self.tree.node_n_children(node_id)

    def do_iter_nth_child(self, parent: Gtk.TreeIter, n: int) -> (bool, Gtk.TreeIter):
        if parent is None:
            node_id = None
        else:
            assert iter.stamp == self.stamp
            if iter.stamp != self.stamp:
                return (False, self._get_invalid_treeiter())
            path = self._get_path(parent)
            node_id = path[-1]
        try:
            child = self.tree.node_nth_child(node_id, n)
            child_path = path + (child.get_id(),)
            return (True, self._get_treeiter(child, child_path))
        except ValueError:
            return (False, self._get_invalid_treeiter())

    def do_iter_parent(self, child: Gtk.TreeIter) -> (bool, Gtk.TreeIter):
        assert child.stamp == self.stamp
        if child.stamp != self.stamp:
            return (False, self._get_invalid_treeiter())

        path = self._get_path(child)
        if len(path) <= 1:
            return (False, self._get_invalid_treeiter())

        parent_path = path[:-1]
        return (True, self._get_treeiter(None, parent_path))

    def do_ref_node(self, iter: Gtk.TreeIter):
        pass  # Do nothing since we don't use it

    def do_unref_node(self, iter: Gtk.TreeIter):
        pass  # Do nothing since we don't use it

    # Gtk.TreeSortable interface implementation
    # TODO?


class TreeModel3(Gtk.TreeModelSort):
    def __init__(self, tree, types):

        self._wrapped = TreeModel2(tree, types)
        super().__init__(self._wrapped)

    def connect_model(self):
        self._wrapped.connect_model()

    def my_get_iter(self, path):
        iter = self._wrapped.my_get_iter(path)
        if iter is None:
            return None
        success, new_iter = self.convert_child_iter_to_iter(iter)
        assert success, "my_get_iter iter conversion failed"
        return new_iter

    def set_column_function(self, column_num: int, column_func):
        return self._wrapped.set_column_function(column_num, column_func)
